require "json"

package = JSON.parse(File.read(File.join(__dir__, "package.json")))

Pod::Spec.new do |s|
  s.name         = "HarmoniqPitchDetector"
  s.version      = package["version"]
  s.summary      = "C++/JSI YIN pitch detector for Harmoniq"
  s.homepage     = "https://harmoniq.ai"
  s.license      = package["license"]
  s.authors      = "Harmoniq"
  s.platforms    = { :ios => "15.1" }
  s.source       = { :path => "." }

  s.source_files = "ios/**/*.{h,mm}", "cpp/**/*.{h,cpp}"
  s.pod_target_xcconfig = {
    "CLANG_CXX_LANGUAGE_STANDARD" => "c++20",
    "HEADER_SEARCH_PATHS" => "$(PODS_TARGET_SRCROOT)/cpp"
  }

  s.dependency "React-Core"
  s.dependency "React-jsi"
  s.dependency "ReactCommon"
end
