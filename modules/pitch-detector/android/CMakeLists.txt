cmake_minimum_required(VERSION 3.13)

project(harmoniq_pitch_detector)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

add_library(
  harmoniq_pitch_detector
  SHARED
  PitchDetectorModule.cpp
  ../cpp/PitchDetectorJsi.cpp
)

target_include_directories(
  harmoniq_pitch_detector
  PUBLIC
  ${CMAKE_CURRENT_SOURCE_DIR}
  PRIVATE
  ../cpp
)

target_compile_options(harmoniq_pitch_detector PRIVATE -O3 -frtti -fexceptions)

find_package(ReactAndroid REQUIRED CONFIG)
find_package(fbjni REQUIRED CONFIG)
find_library(LOG_LIB log)

target_link_libraries(
  harmoniq_pitch_detector
  ReactAndroid::jsi
  ReactAndroid::reactnative
  fbjni::fbjni
  ${LOG_LIB}
  android
)
