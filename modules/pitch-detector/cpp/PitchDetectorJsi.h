#pragma once

#include <jsi/jsi.h>

namespace harmoniq::pitch {

/**
 * Installs the synchronous pitch detector on `globalThis.__harmoniqPitch`.
 *
 * The bridge owns no microphone resources: callers feed PCM frames from the
 * existing react-native-audio-api recorder into `processPcm`.
 */
void install(facebook::jsi::Runtime& runtime);

/** Removes the bridge from the global object. */
void uninstall(facebook::jsi::Runtime& runtime);

} // namespace harmoniq::pitch
