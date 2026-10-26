#include "PitchDetectorJsi.h"

#include <algorithm>
#include <atomic>
#include <cmath>
#include <condition_variable>
#include <cstddef>
#include <memory>
#include <mutex>
#include <thread>
#include <vector>

namespace harmoniq::pitch {
namespace {

constexpr int kAnalysisWindow = 2048;
constexpr int kRingCapacity = 4096;
constexpr double kMinHz = 70.0;
constexpr double kMaxHz = 1000.0;
constexpr double kMinRms = 0.003;
constexpr double kYinThreshold = 0.15;

class PitchDetectorState {
 public:
  PitchDetectorState() : worker_(&PitchDetectorState::workerLoop, this) {}

  ~PitchDetectorState() {
    {
      std::lock_guard<std::mutex> lock(mutex_);
      running_ = false;
    }
    condition_.notify_all();
    if (worker_.joinable()) {
      worker_.join();
    }
  }

  void reset() {
    std::lock_guard<std::mutex> lock(mutex_);
    std::fill(ring_.begin(), ring_.end(), 0.0f);
    writeIndex_ = 0;
    available_ = 0;
    pending_ = false;
    hz_.store(0.0);
    rms_.store(0.0);
    peakAbs_.store(0.0);
  }

  void push(const float* samples, std::size_t count, double sampleRate) {
    if (samples == nullptr || count == 0) return;
    count = std::min(count, static_cast<std::size_t>(kRingCapacity));

    double sumSquares = 0.0;
    double peak = 0.0;
    for (std::size_t i = 0; i < count; i += 1) {
      const double value = samples[i];
      sumSquares += value * value;
      peak = std::max(peak, std::abs(value));
    }
    const double chunkRms = std::sqrt(sumSquares / static_cast<double>(count));

    {
      std::lock_guard<std::mutex> lock(mutex_);
      for (std::size_t i = 0; i < count; i += 1) {
        ring_[(writeIndex_ + i) % kRingCapacity] = samples[i];
      }
      writeIndex_ = (writeIndex_ + count) % kRingCapacity;
      available_ = std::min(available_ + count, static_cast<std::size_t>(kRingCapacity));
      sampleRate_ = sampleRate;
      pending_ = true;
    }

    rms_.store(chunkRms);
    peakAbs_.store(peak);
    if (chunkRms < kMinRms) {
      hz_.store(0.0);
    }
    condition_.notify_one();
  }

  double pitchHz() const {
    return hz_.load();
  }

  double rms() const {
    return rms_.load();
  }

  double peakAbs() const {
    return peakAbs_.load();
  }

 private:
  void workerLoop() {
    std::unique_lock<std::mutex> lock(mutex_);
    while (true) {
      condition_.wait(lock, [this] {
        return !running_ || (pending_ && available_ >= kAnalysisWindow);
      });
      if (!running_) return;

      pending_ = false;
      const std::size_t start = (writeIndex_ + kRingCapacity - kAnalysisWindow) % kRingCapacity;
      for (int i = 0; i < kAnalysisWindow; i += 1) {
        window_[i] = ring_[(start + i) % kRingCapacity];
      }
      const double sampleRate = sampleRate_;
      lock.unlock();
      analyze(sampleRate);
      lock.lock();
    }
  }

  void analyze(double sampleRate) {
    if (rms_.load() < kMinRms) {
      hz_.store(0.0);
      return;
    }

    const int window = kAnalysisWindow;
    const int half = window / 2;
    const int minLag = std::max(2, static_cast<int>(std::floor(sampleRate / kMaxHz)));
    const int maxLag = std::min(half - 1, static_cast<int>(std::ceil(sampleRate / kMinHz)));
    if (maxLag <= minLag) {
      hz_.store(0.0);
      return;
    }

    diff_[0] = 0.0;
    for (int lag = 1; lag <= maxLag; lag += 1) {
      double sum = 0.0;
      for (int i = 0; i < half; i += 1) {
        const double delta = window_[i] - window_[i + lag];
        sum += delta * delta;
      }
      diff_[lag] = sum;
    }

    double runningSum = 0.0;
    diff_[0] = 1.0;
    for (int lag = 1; lag <= maxLag; lag += 1) {
      runningSum += diff_[lag];
      diff_[lag] = runningSum > 0.0 ? (diff_[lag] * lag) / runningSum : 1.0;
    }

    int bestLag = -1;
    for (int lag = minLag; lag <= maxLag; lag += 1) {
      if (diff_[lag] < kYinThreshold) {
        bestLag = lag;
        break;
      }
    }
    if (bestLag < 0) {
      double bestValue = diff_[minLag];
      bestLag = minLag;
      for (int lag = minLag + 1; lag <= maxLag; lag += 1) {
        if (diff_[lag] < bestValue) {
          bestValue = diff_[lag];
          bestLag = lag;
        }
      }
    }

    double refinedLag = static_cast<double>(bestLag);
    if (bestLag > 1 && bestLag < maxLag) {
      const double previous = diff_[bestLag - 1];
      const double current = diff_[bestLag];
      const double next = diff_[bestLag + 1];
      const double denominator = 2.0 * (2.0 * current - next - previous);
      if (denominator != 0.0) {
        refinedLag += (next - previous) / denominator;
      }
    }

    const double hz = sampleRate / refinedLag;
    if (!std::isfinite(hz) || hz < kMinHz || hz > kMaxHz) {
      hz_.store(0.0);
      return;
    }
    hz_.store(hz);
  }

  mutable std::mutex mutex_;
  std::condition_variable condition_;
  bool running_ = true;
  bool pending_ = false;
  std::vector<float> ring_ = std::vector<float>(kRingCapacity, 0.0f);
  std::vector<float> window_ = std::vector<float>(kAnalysisWindow, 0.0f);
  std::vector<double> diff_ = std::vector<double>(kAnalysisWindow, 0.0);
  std::size_t writeIndex_ = 0;
  std::size_t available_ = 0;
  double sampleRate_ = 44100.0;
  std::atomic<double> hz_{0.0};
  std::atomic<double> rms_{0.0};
  std::atomic<double> peakAbs_{0.0};
  // Declared last so every field above is initialized before the worker starts.
  std::thread worker_;
};

facebook::jsi::Value makeStart(facebook::jsi::Runtime& runtime, std::shared_ptr<PitchDetectorState> state) {
  return facebook::jsi::Function::createFromHostFunction(
      runtime,
      facebook::jsi::PropNameID::forAscii(runtime, "start"),
      0,
      [state](facebook::jsi::Runtime&, const facebook::jsi::Value&, const facebook::jsi::Value*, std::size_t) {
        state->reset();
        return facebook::jsi::Value::undefined();
      });
}

facebook::jsi::Value makeProcessPcm(
    facebook::jsi::Runtime& runtime,
    std::shared_ptr<PitchDetectorState> state) {
  return facebook::jsi::Function::createFromHostFunction(
      runtime,
      facebook::jsi::PropNameID::forAscii(runtime, "processPcm"),
      2,
      [state](
          facebook::jsi::Runtime& runtime,
          const facebook::jsi::Value&,
          const facebook::jsi::Value* args,
          std::size_t count) {
        if (count < 2 || !args[0].isObject() || !args[1].isNumber()) {
          return facebook::jsi::Value::undefined();
        }

        auto samples = args[0].asObject(runtime);
        auto bufferValue = samples.getProperty(runtime, "buffer");
        if (!bufferValue.isObject()) {
          return facebook::jsi::Value::undefined();
        }
        auto arrayBufferObject = bufferValue.asObject(runtime);
        if (!arrayBufferObject.isArrayBuffer(runtime)) {
          return facebook::jsi::Value::undefined();
        }

        const auto arrayBuffer = arrayBufferObject.getArrayBuffer(runtime);
        const auto byteOffset = static_cast<std::size_t>(
            samples.getProperty(runtime, "byteOffset").getNumber());
        const auto length = static_cast<std::size_t>(
            samples.getProperty(runtime, "length").getNumber());
        const std::size_t byteLength = length * sizeof(float);
        if (byteOffset + byteLength > arrayBuffer.size(runtime)) {
          return facebook::jsi::Value::undefined();
        }

        const auto* data =
            reinterpret_cast<const float*>(arrayBuffer.data(runtime) + byteOffset);
        state->push(data, length, args[1].getNumber());
        return facebook::jsi::Value::undefined();
      });
}

facebook::jsi::Value makeReadNumber(
    facebook::jsi::Runtime& runtime,
    const char* name,
    const std::shared_ptr<PitchDetectorState>& state,
    double (PitchDetectorState::*reader)() const) {
  return facebook::jsi::Function::createFromHostFunction(
      runtime,
      facebook::jsi::PropNameID::forAscii(runtime, name),
      0,
      [state, reader](
          facebook::jsi::Runtime&, const facebook::jsi::Value&, const facebook::jsi::Value*, std::size_t) {
        return facebook::jsi::Value((state.get()->*reader)());
      });
}

facebook::jsi::Value makeStop(facebook::jsi::Runtime& runtime, std::shared_ptr<PitchDetectorState> state) {
  return facebook::jsi::Function::createFromHostFunction(
      runtime,
      facebook::jsi::PropNameID::forAscii(runtime, "stop"),
      0,
      [state](facebook::jsi::Runtime&, const facebook::jsi::Value&, const facebook::jsi::Value*, std::size_t) {
        state->reset();
        return facebook::jsi::Value::undefined();
      });
}

} // namespace

void install(facebook::jsi::Runtime& runtime) {
  auto state = std::make_shared<PitchDetectorState>();
  facebook::jsi::Object bridge(runtime);
  bridge.setProperty(runtime, "start", makeStart(runtime, state));
  bridge.setProperty(runtime, "processPcm", makeProcessPcm(runtime, state));
  bridge.setProperty(runtime, "getPitchHz", makeReadNumber(runtime, "getPitchHz", state, &PitchDetectorState::pitchHz));
  bridge.setProperty(runtime, "getRms", makeReadNumber(runtime, "getRms", state, &PitchDetectorState::rms));
  bridge.setProperty(
      runtime, "getPeakAbs", makeReadNumber(runtime, "getPeakAbs", state, &PitchDetectorState::peakAbs));
  bridge.setProperty(runtime, "stop", makeStop(runtime, state));
  runtime.global().setProperty(runtime, "__harmoniqPitch", std::move(bridge));
}

void uninstall(facebook::jsi::Runtime& runtime) {
  runtime.global().setProperty(runtime, "__harmoniqPitch", facebook::jsi::Value::undefined());
}

} // namespace harmoniq::pitch
