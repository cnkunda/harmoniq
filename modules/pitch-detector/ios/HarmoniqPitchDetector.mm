#import <React/RCTBridgeModule.h>
#import <ReactCommon/RCTTurboModule.h>
#import <ReactCommon/RCTTurboModuleWithJSIBindings.h>
#import <jsi/jsi.h>

#import "PitchDetectorJsi.h"

#include <memory>
#include <utility>

using namespace facebook::react;
using namespace facebook::jsi;

namespace {

class HarmoniqPitchDetectorTurboModule final : public TurboModule {
 public:
  explicit HarmoniqPitchDetectorTurboModule(std::shared_ptr<CallInvoker> jsInvoker)
      : TurboModule("HarmoniqPitchDetector", std::move(jsInvoker)) {}
};

} // namespace

@interface HarmoniqPitchDetector : NSObject <RCTBridgeModule, RCTTurboModuleWithJSIBindings>
@end

@implementation HarmoniqPitchDetector

RCT_EXPORT_MODULE()

+ (BOOL)requiresMainQueueSetup
{
  return NO;
}

- (std::shared_ptr<TurboModule>)getTurboModule:(const ObjCTurboModule::InitParams &)params
{
  return std::make_shared<HarmoniqPitchDetectorTurboModule>(params.jsInvoker);
}

- (void)installJSIBindingsWithRuntime:(jsi::Runtime &)runtime
                          callInvoker:(const std::shared_ptr<CallInvoker> &)callInvoker
{
  harmoniq::pitch::install(runtime);
}

@end
