cmake_minimum_required(VERSION 3.14)

project(rapidjson LANGUAGES CXX)

set(CMAKE_INCLUDE_CURRENT_DIR ON)
set(CMAKE_CXX_STANDARD 11)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

add_library(rapidjson SHARED
  rapidjson.cpp
  rapidjson.h
  allocators.h
  cursorstreamwrapper.h
  document.h
  encodedstream.h
  encodings.h
  filereadstream.h
  filewritestream.h
  fwd.h
  istreamwrapper.h
  memorybuffer.h
  memorystream.h
  ostreamwrapper.h
  pointer.h
  prettywriter.h
  pybytesbuffer.h
  pywritestreamwrapper.h
  rapidjson.h
  reader.h
  schema.h
  stream.h
  stringbuffer.h
  uri.h
  writer.h
  serializejson.h
  rapidjson.cpp



)

target_compile_definitions(rapidjson PRIVATE RAPIDJSON_LIBRARY)
find_package(PythonLibs REQUIRED)
include_directories(${PYTHON_INCLUDE_DIRS})
target_link_libraries(rapidjson ${PYTHON_LIBRARIES})
