module.exports = {
  dependency: {
    platforms: {
      android: {
        sourceDir: 'android',
        libraryName: 'HarmoniqPitchDetector',
        cmakeListsPath: 'CodegenStub/CMakeLists.txt',
        cxxModuleCMakeListsModuleName: 'harmoniq_pitch_detector',
        cxxModuleCMakeListsPath: 'CMakeLists.txt',
        cxxModuleHeaderName: 'PitchDetectorModule',
      },
    },
  },
}
