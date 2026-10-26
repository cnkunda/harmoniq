#include "PitchDetectorModule.h"

#include "PitchDetectorJsi.h"

#include <utility>

namespace facebook::react {

PitchDetectorModule::PitchDetectorModule(std::shared_ptr<CallInvoker> jsInvoker)
    : TurboModule(kModuleName, std::move(jsInvoker)) {}

void PitchDetectorModule::installJSIBindingsWithRuntime(jsi::Runtime& runtime) {
  harmoniq::pitch::install(runtime);
}

std::shared_ptr<TurboModule> HarmoniqPitchDetector_ModuleProvider(
    const std::string&,
    const JavaTurboModule::InitParams&) {
  return nullptr;
}

} // namespace facebook::react
