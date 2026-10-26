cmake_minimum_required(VERSION 3.13)

project(harmoniq_pitch_detector_codegen_stub)

# React Native autolinking links `react_codegen_<libraryName>` for every
# dependency that declares a libraryName. This module has no codegen spec, so
# this stub satisfies that link.
add_library(
  react_codegen_HarmoniqPitchDetector
  STATIC
  ../HarmoniqPitchDetectorStub.cpp
)
