#pragma once

#include <ReactCommon/CallInvoker.h>
#include <ReactCommon/JavaTurboModule.h>
#include <ReactCommon/TurboModule.h>
#include <ReactCommon/TurboModuleWithJSIBindings.h>

#include <memory>
#include <string>

namespace facebook::react {

class PitchDetectorModule final : public TurboModule, public TurboModuleWithJSIBindings {
 public:
  static constexpr const char* kModuleName = "HarmoniqPitchDetector";

  explicit PitchDetectorModule(std::shared_ptr<CallInvoker> jsInvoker);

 private:
  void installJSIBindingsWithRuntime(jsi::Runtime& runtime) override;
};

/**
 * Autolinking emits a Java provider call for every library with a `libraryName`
 * (which pure C++ modules need so their header/provider is generated). This
 * module has no Java side, so the Java lookup always misses.
 */
std::shared_ptr<TurboModule> HarmoniqPitchDetector_ModuleProvider(
    const std::string& moduleName,
    const JavaTurboModule::InitParams& params);

} // namespace facebook::react
