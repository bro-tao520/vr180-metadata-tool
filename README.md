# VR180 Metadata Injector

A lightweight, extremely fast, and memory-efficient GUI tool to inject standard VR180 (Left-Right, Equirectangular) metadata into MP4 videos, or completely clear corrupted metadata. 

Designed specifically for VR creators dealing with massive video files (e.g., 50GB+ 8K ProRes/H.265 files).

## 🚀 Why this tool?
Traditional metadata injection tools load the entire video into RAM, which causes memory overflow (OOM) or heavy disk swapping when processing large VR video files. 

This tool utilizes a **Streaming (Chunk-based) processing logic**:
- **Zero Memory Bloat**: Uses a fixed 8MB buffer regardless of whether your video is 1GB or 100GB.
- **Maximum Speed**: Achieves pure sequential read/write speeds, maxing out your SSD's bandwidth.
- **Clean Output**: Uses FFmpeg to strip conflicting metadata before injecting the standard Google Spatial Media XML.

## ✨ Features
* **Two Processing Modes**:
  1. **Inject VR180 Metadata**: Cleans old metadata and injects standard VR180 tags.
  2. **Clear Metadata Only**: Strips all metadata to fix playback or re-encoding issues (e.g., Premiere Pro export bugs).
* **Flexible Selection**: 
  * Select specific files (Single or Multiple selection).
  * Select an entire folder for automatic batch processing.
* **Smart Skipping**: Automatically ignores already processed files (`_injected.mp4` or `_cleared.mp4`) in batch mode to prevent infinite loops.

## 📦 Prerequisites
1. **Python 3.x** installed on your system (Tkinter is included by default).
2. **FFmpeg** installed and added to your system's PATH (or placed in the same directory as the script).

## 🛠️ How to Use
1. Clone this repository or download the `VR_metadata_tool.py` script.
2. Run the script:
   ```bash
   python VR_metadata_tool.py
   ```
3. A GUI window will appear with two main sections:
   * **Option 1**: Click to select specific video files.
   * **Option 2**: Click to select a folder for batch processing.
4. Choose either **INJECT VR180** or **CLEAR Metadata**.
5. The output files will be saved in the same directory with `_injected.mp4` or `_cleared.mp4` suffixes.

## 📝 Compatibility
The injected metadata follows the standard `Google Spatial Media` format. Videos processed with this tool are fully recognized as VR180 by:
- YouTube VR
- Meta Quest TV
- Adobe Premiere Pro
- DeoVR / Skybox VR Player

## 🤝 Contributing
Contributions, issues, and feature requests are welcome! 
If this tool helped you process massive VR videos without OOM crashes, or saved you hours of re-encoding time, please consider giving it a ⭐ **Star**!

## 📄 License
This project is licensed under the MIT License - feel free to use, modify, and distribute it!
