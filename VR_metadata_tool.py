#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VR180 Metadata Tool - /moov/trak/uuid Injection
================================================

A professional tool for injecting and clearing VR180 spatial metadata in video files.
Supports batch processing with streaming for ultra-large files (100GB+).

Author: bro-tao520
License: MIT
Repository: https://github.com/bro-tao520/vr180-metadata-tool

Features:
  - Stream-based processing: 8MB buffer, handles 100GB+ files with minimal memory
  - FFmpeg integration: Safe metadata removal with -map_metadata -1
  - Lossless processing: Full 'copy' mode, no re-encoding
  - Batch operations: Single file, folder batch, or selective processing
  - Duplicate prevention: Automatic detection of already-processed files
  - Cross-platform: Windows, Linux, macOS support

Usage:
  python vr180_metadata_tool.py
"""

import os
import struct
import subprocess
import tkinter as tk
import gc
from tkinter import filedialog, messagebox, ttk

# Supported video file extensions
VIDEO_EXTENSIONS = ('.mp4', '.mkv', '.mov', '.avi', '.webm', '.flv', '.m4v')

# Extensions suitable for -movflags +faststart optimization
FASTSTART_EXTENSIONS = ('.mp4', '.mov', '.m4v')


def inject_google_vr180_metadata_to_udta(file_path):
    """
    Stream-based safe processing for large files:
    
    Only loads moov (few MB) into memory for modification, performs 8MB chunked
    streaming copy for mdat (huge video data). Extremely low memory footprint,
    supports 100GB+ ultra-large videos, completely solves OOM issues.
    
    Injection path: /moov/trak/uuid
    Does not write st3d/sv3d or udta.
    
    Args:
        file_path (str): Path to the video file to inject metadata into
        
    Raises:
        Exception: If video trak not found, resolution unreadable, or offset overflow
    """
    temp_file = file_path + ".tmp"
    
    with open(file_path, 'rb') as fin, open(temp_file, 'wb') as fout:
        mdat_pos = -1
        
        while True:
            header = fin.read(8)
            if not header:
                break
            if len(header) < 8:
                fout.write(header)
                break
                
            box_size, box_type = struct.unpack('>I4s', header)
            header_size = 8
            actual_size = box_size
            
            if box_size == 1:
                extra = fin.read(8)
                header += extra
                actual_size = struct.unpack('>Q', extra)[0]
                header_size = 16
            elif box_size == 0:
                current_pos = fin.tell()
                fin.seek(0, os.SEEK_END)
                end_pos = fin.tell()
                fin.seek(current_pos, os.SEEK_SET)
                actual_size = (end_pos - current_pos) + header_size
                
            box_type_str = box_type.decode('ascii', errors='ignore')
            
            # Process mdat (huge video data): stream copy, never consume memory
            if box_type_str == 'mdat':
                mdat_pos = fout.tell()
                fout.write(header)
                bytes_to_copy = actual_size - header_size
                chunk_size = 8 * 1024 * 1024  # 8MB buffer
                while bytes_to_copy > 0:
                    read_size = min(chunk_size, bytes_to_copy)
                    chunk = fin.read(read_size)
                    if not chunk:
                        break
                    fout.write(chunk)
                    bytes_to_copy -= len(chunk)
                    
            # Process moov (metadata): load into memory for parsing and injection
            elif box_type_str == 'moov':
                moov_start_pos = fin.tell() - header_size
                moov_payload = fin.read(actual_size - header_size)
                moov_data = bytearray(header + moov_payload)
                
                def read_u32(pos):
                    return struct.unpack(">I", moov_data[pos:pos + 4])[0]
                    
                def write_u32(pos, value):
                    moov_data[pos:pos + 4] = struct.pack(">I", value)
                    
                def read_u64(pos):
                    return struct.unpack(">Q", moov_data[pos:pos + 8])[0]
                    
                def write_u64(pos, value):
                    moov_data[pos:pos + 8] = struct.pack(">Q", value)
                    
                def get_children(pos, size, hdr_size):
                    """Parse child boxes within a parent box"""
                    children = []
                    p = pos + hdr_size
                    end = pos + size
                    while p + 8 <= end and p + 8 <= len(moov_data):
                        c_size = read_u32(p)
                        c_name = moov_data[p + 4:p + 8]
                        if c_size == 1:
                            if p + 16 > end or p + 16 > len(moov_data):
                                break
                            c_size = read_u64(p + 8)
                            c_hdr = 16
                        elif c_size == 0:
                            c_size = end - p
                            c_hdr = 8
                        else:
                            c_hdr = 8
                        if c_size < c_hdr or p + c_size > len(moov_data):
                            break
                        children.append((c_name, p, c_size, c_hdr))
                        p += c_size
                    return children

                target_trak_pos = -1
                target_trak_size = 0
                target_trak_hdr = 8
                width = 0
                height = 0
                video_entry_type = b''
                
                moov_children = get_children(0, len(moov_data), header_size)
                
                # Find video trak and extract resolution
                for t_name, t_pos, t_size, t_hdr in moov_children:
                    if t_name != b'trak':
                        continue
                    trak_children = get_children(t_pos, t_size, t_hdr)
                    is_video_trak = False
                    found_width = 0
                    found_height = 0
                    found_entry_type = b''
                    
                    for m_name, m_pos, m_size, m_hdr in trak_children:
                        if m_name != b'mdia':
                            continue
                        mdia_children = get_children(m_pos, m_size, m_hdr)
                        minf_box = None
                        for md_name, md_pos, md_size, md_hdr in mdia_children:
                            if md_name == b'hdlr':
                                handler_type_pos = md_pos + md_hdr + 8
                                if handler_type_pos + 4 <= len(moov_data):
                                    if moov_data[handler_type_pos:handler_type_pos + 4] == b'vide':
                                        is_video_trak = True
                            elif md_name == b'minf':
                                minf_box = (md_pos, md_size, md_hdr)
                        
                        if not is_video_trak or not minf_box:
                            continue
                        minf_children = get_children(minf_box[0], minf_box[1], minf_box[2])
                        for mi_name, mi_pos, mi_size, mi_hdr in minf_children:
                            if mi_name != b'stbl':
                                continue
                            stbl_children = get_children(mi_pos, mi_size, mi_hdr)
                            for st_name, st_pos, st_size, st_hdr in stbl_children:
                                if st_name != b'stsd':
                                    continue
                                entry_start = st_pos + st_hdr + 8
                                if entry_start + 36 > len(moov_data):
                                    continue
                                entry_size = read_u32(entry_start)
                                found_entry_type = moov_data[entry_start + 4:entry_start + 8]
                                if entry_size < 36:
                                    continue
                                found_width = struct.unpack(">H", moov_data[entry_start + 32:entry_start + 34])[0]
                                found_height = struct.unpack(">H", moov_data[entry_start + 34:entry_start + 36])[0]
                                break
                            if found_width > 0:
                                break
                        if found_width > 0:
                            break
                    
                    if is_video_trak and found_width > 0 and found_height > 0:
                        target_trak_pos = t_pos
                        target_trak_size = t_size
                        target_trak_hdr = t_hdr
                        width = found_width
                        height = found_height
                        video_entry_type = found_entry_type
                        break

                if target_trak_pos == -1 or width <= 0 or height <= 0:
                    raise Exception("Video trak not found or resolution unreadable.")
                    
                print(f"Detected video sample entry: {video_entry_type.decode('ascii', 'ignore')}, "
                      f"resolution: {width}x{height}")

                # Construct XML metadata for VR180
                SPATIAL_UUID = b'\xff\xcc\x82\x63\xf8\x55\x4a\x93\x88\x14\x58\x7a\x02\x52\x1f\xdd'
                xml_metadata = (
                    f'<?xml version="1.0"?><rdf:SphericalVideo\n'
                    f'xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"\n'
                    f'xmlns:GSpherical="http://ns.google.com/videos/1.0/spherical/">'
                    f'<GSpherical:Spherical>true</GSpherical:Spherical>'
                    f'<GSpherical:Stitched>true</GSpherical:Stitched>'
                    f'<GSpherical:StitchingSoftware>Spherical Metadata Tool</GSpherical:StitchingSoftware>'
                    f'<GSpherical:ProjectionType>equirectangular</GSpherical:ProjectionType>'
                    f'<GSpherical:StereoMode>left-right</GSpherical:StereoMode>'
                    f'<GSpherical:CroppedAreaImageWidthPixels>{width}</GSpherical:CroppedAreaImageWidthPixels>'
                    f'<GSpherical:CroppedAreaImageHeightPixels>{height}</GSpherical:CroppedAreaImageHeightPixels>'
                    f'<GSpherical:FullPanoWidthPixels>{width * 2}</GSpherical:FullPanoWidthPixels>'
                    f'<GSpherical:FullPanoHeightPixels>{height}</GSpherical:FullPanoHeightPixels>'
                    f'<GSpherical:CroppedAreaLeftPixels>{width // 2}</GSpherical:CroppedAreaLeftPixels>'
                    f'<GSpherical:CroppedAreaTopPixels>0</GSpherical:CroppedAreaTopPixels>'
                    f'</rdf:SphericalVideo>'
                ).encode('utf-8')
                
                uuid_box_payload = SPATIAL_UUID + xml_metadata
                uuid_box_size = 8 + len(uuid_box_payload)
                uuid_box = struct.pack(">I4s", uuid_box_size, b"uuid") + uuid_box_payload
                added_len = len(uuid_box)
                
                insert_pos = target_trak_pos + target_trak_size
                absolute_insert_pos = moov_start_pos + insert_pos
                
                # Fix stco/co64 offsets
                if mdat_pos == -1:
                    def find_all_offset_boxes(pos, size, hdr_size):
                        """Recursively find all stco/co64 boxes"""
                        boxes = []
                        children = get_children(pos, size, hdr_size)
                        for c_name, c_pos, c_size, c_hdr in children:
                            if c_name in [b'stco', b'co64']:
                                boxes.append((c_name, c_pos, c_hdr))
                            elif c_name in [b'trak', b'mdia', b'minf', b'stbl']:
                                boxes.extend(find_all_offset_boxes(c_pos, c_size, c_hdr))
                        return boxes
                        
                    offset_boxes = find_all_offset_boxes(0, len(moov_data), header_size)
                    fixed_count = 0
                    for b_name, b_pos, b_hdr in offset_boxes:
                        count_pos = b_pos + b_hdr + 4
                        if count_pos + 4 > len(moov_data):
                            continue
                        count = read_u32(count_pos)
                        offset_pos = b_pos + b_hdr + 8
                        for _ in range(count):
                            if b_name == b'co64':
                                if offset_pos + 8 > len(moov_data):
                                    break
                                old_offset = read_u64(offset_pos)
                                if old_offset >= absolute_insert_pos:
                                    write_u64(offset_pos, old_offset + added_len)
                                    fixed_count += 1
                                offset_pos += 8
                            else:
                                if offset_pos + 4 > len(moov_data):
                                    break
                                old_offset = read_u32(offset_pos)
                                if old_offset >= absolute_insert_pos:
                                    new_offset = old_offset + added_len
                                    if new_offset > 0xFFFFFFFF:
                                        raise Exception(
                                            "stco offset exceeds 32-bit, needs co64 conversion; "
                                            "current version does not auto-convert."
                                        )
                                    write_u32(offset_pos, new_offset)
                                    fixed_count += 1
                                offset_pos += 4
                    print(f"moov before mdat, fixed stco/co64 offsets: {fixed_count}")
                else:
                    print("moov after mdat, no stco/co64 offset fix needed.")
                
                # Update trak and moov size fields
                if target_trak_hdr == 8:
                    write_u32(target_trak_pos, target_trak_size + added_len)
                else:
                    write_u64(target_trak_pos + 8, target_trak_size + added_len)

                if header_size == 8:
                    write_u32(0, len(moov_data) + added_len)
                else:
                    write_u64(8, len(moov_data) + added_len)
                    
                # Insert uuid box
                moov_data[insert_pos:insert_pos] = uuid_box
                fout.write(moov_data)
                
            # Other boxes (ftyp, free, etc.): stream copy
            else:
                fout.write(header)
                bytes_to_copy = actual_size - header_size
                chunk_size = 8 * 1024 * 1024
                while bytes_to_copy > 0:
                    read_size = min(chunk_size, bytes_to_copy)
                    chunk = fin.read(read_size)
                    if not chunk:
                        break
                    fout.write(chunk)
                    bytes_to_copy -= len(chunk)

    # Replace original file with new one
    try:
        os.replace(temp_file, file_path)
    except Exception as e:
        print(f"File replacement failed: {e}")
        raise
        
    print("Google VR180 metadata injection completed: /moov/trak/uuid.")


class VRMetadataToolApp:
    """Main GUI application for VR180 metadata injection and clearing"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("VR180 Metadata Tool")
        self.root.geometry("780x570")
        self.root.minsize(700, 520)

        self.file_list = []
        self.style = ttk.Style()
        self.style.theme_use("clam")

        self.create_widgets()

    def create_widgets(self):
        """Create all GUI widgets"""
        main_frame = ttk.Frame(self.root, padding="15")
        main_frame.pack(fill=tk.BOTH, expand=True)

        title_label = ttk.Label(
            main_frame,
            text="VR180 Metadata Tool",
            font=("Helvetica", 15, "bold")
        )
        title_label.pack(pady=(0, 10))

        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=5)

        btn_files = ttk.Button(
            btn_frame,
            text="Select Files (Multiple)",
            command=self.browse_files
        )
        btn_files.pack(side=tk.LEFT, padx=(0, 10))

        btn_dir = ttk.Button(
            btn_frame,
            text="Select Folder",
            command=self.browse_directory
        )
        btn_dir.pack(side=tk.LEFT, padx=(0, 10))

        btn_clear_list = ttk.Button(
            btn_frame,
            text="Clear List",
            command=self.clear_list
        )
        btn_clear_list.pack(side=tk.RIGHT)

        list_frame = ttk.Frame(main_frame)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=10)

        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.file_listbox = tk.Listbox(
            list_frame,
            yscrollcommand=scrollbar.set,
            selectmode=tk.EXTENDED,
            font=("Helvetica", 10)
        )
        self.file_listbox.pack(fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.file_listbox.yview)

        self.status_label = ttk.Label(
            main_frame,
            text="Files to process: 0",
            font=("Helvetica", 10, "bold")
        )
        self.status_label.pack(anchor=tk.W, pady=(0, 5))

        action_frame = ttk.LabelFrame(main_frame, text=" Select Operation ", padding="10")
        action_frame.pack(fill=tk.X, pady=(5, 10))

        self.action_var = tk.StringVar(value="inject")

        # Injection mode: Write Google Spatial UUID to /moov/trak/uuid
        # Does not write st3d/sv3d or udta
        r_inject = ttk.Radiobutton(
            action_frame,
            text="Inject Metadata",
            variable=self.action_var,
            value="inject"
        )
        r_inject.pack(anchor=tk.W, pady=2)

        # Clear mode: Use FFmpeg to safely remove all metadata
        # Performs re-muxing without re-encoding
        r_clear = ttk.Radiobutton(
            action_frame,
            text="Clear Metadata",
            variable=self.action_var,
            value="clear"
        )
        r_clear.pack(anchor=tk.W, pady=2)

        self.progress_bar = ttk.Progressbar(
            main_frame,
            orient=tk.HORIZONTAL,
            mode='determinate'
        )
        self.progress_bar.pack(fill=tk.X, pady=(0, 10))

        self.btn_start = ttk.Button(
            main_frame,
            text="Start Processing",
            command=self.process_files,
            state=tk.DISABLED
        )
        self.btn_start.pack(fill=tk.X, ipady=6)

    def update_listbox(self):
        """Update file list display"""
        self.file_listbox.delete(0, tk.END)

        for file in self.file_list:
            self.file_listbox.insert(tk.END, file)

        count = len(self.file_list)
        self.status_label.config(text=f"Files to process: {count}")

        if count > 0:
            self.btn_start.config(state=tk.NORMAL)
        else:
            self.btn_start.config(state=tk.DISABLED)

    def browse_files(self):
        """Open file selection dialog"""
        files_selected = filedialog.askopenfilenames(
            title="Select video files",
            filetypes=[
                ("Video files", "*.mp4 *.mkv *.mov *.avi *.webm *.flv *.m4v"),
                ("All files", "*.*")
            ]
        )

        if files_selected:
            for file in files_selected:
                if file not in self.file_list:
                    self.file_list.append(file)

            self.update_listbox()

    def browse_directory(self):
        """Open directory selection dialog"""
        dir_selected = filedialog.askdirectory(title="Select folder")

        if dir_selected:
            for entry in os.scandir(dir_selected):
                if entry.is_file() and entry.name.lower().endswith(VIDEO_EXTENSIONS):
                    if entry.path not in self.file_list:
                        self.file_list.append(entry.path)

            self.update_listbox()

    def clear_list(self):
        """Clear file list"""
        self.file_list.clear()
        self.update_listbox()
        self.progress_bar['value'] = 0

    def build_ffmpeg_clean_command(self, input_file, output_file, ext, use_faststart=True):
        """
        Build FFmpeg metadata cleaning command.

        Args:
            input_file (str): Input video file path
            output_file (str): Output video file path
            ext (str): File extension
            use_faststart (bool): Whether to use -movflags +faststart
                                 True: Output /ftyp /moov /mdat (optimized for streaming)
                                 False: Output /ftyp /free /mdat /moov (standard structure)

        Returns:
            list: FFmpeg command as list of arguments
        """
        cmd = [
            'ffmpeg',
            '-y',
            '-i', input_file,
            '-map', '0',
            '-map_metadata', '-1',
            '-map_chapters', '-1',
            '-c', 'copy'
        ]

        if use_faststart and ext.lower() in FASTSTART_EXTENSIONS:
            cmd += ['-movflags', '+faststart']

        cmd.append(output_file)
        return cmd

    def process_files(self):
        """Process all files in the list"""
        if not self.file_list:
            return

        total_files = len(self.file_list)
        success_count = 0
        fail_count = 0
        mode = self.action_var.get()

        self.btn_start.config(state=tk.DISABLED, text="Processing...")
        self.progress_bar['maximum'] = total_files
        self.progress_bar['value'] = 0

        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        for index, input_file in enumerate(self.file_list):
            if not os.path.exists(input_file):
                fail_count += 1
                continue

            dir_name, file_name = os.path.split(input_file)
            name, ext = os.path.splitext(file_name)
            ext_lower = ext.lower()

            try:
                self.file_listbox.selection_clear(0, tk.END)
                self.file_listbox.selection_set(index)
                self.file_listbox.see(index)
                self.root.update()

                if mode == "clear":
                    output_file = os.path.join(dir_name, f"{name}_clear{ext}")

                    cmd = self.build_ffmpeg_clean_command(
                        input_file=input_file,
                        output_file=output_file,
                        ext=ext_lower,
                        use_faststart=True
                    )

                    result = subprocess.run(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        startupinfo=startupinfo,
                        text=True
                    )

                    if result.returncode == 0:
                        success_count += 1
                    else:
                        fail_count += 1
                        print(f"FFmpeg clear failed: {input_file}")
                        print(result.stderr)

                else:
                    if ext_lower not in FASTSTART_EXTENSIONS:
                        fail_count += 1
                        print(f"Skipping non-MP4/MOV/M4V file: {input_file}")
                        continue

                    output_file = os.path.join(dir_name, f"{name}_VR180_injected{ext}")

                    cmd = self.build_ffmpeg_clean_command(
                        input_file=input_file,
                        output_file=output_file,
                        ext=ext_lower,
                        use_faststart=False
                    )

                    result = subprocess.run(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        startupinfo=startupinfo,
                        text=True
                    )

                    if result.returncode != 0:
                        fail_count += 1
                        print(f"FFmpeg pre-processing failed: {input_file}")
                        print(result.stderr)
                    else:
                        try:
                            inject_google_vr180_metadata_to_udta(output_file)
                            success_count += 1
                        except Exception as e:
                            fail_count += 1
                            print(f"Injection failed: {input_file}")
                            print(str(e))

                            if os.path.exists(output_file):
                                try:
                                    os.remove(output_file)
                                except Exception:
                                    pass

            except Exception as e:
                fail_count += 1
                print(f"Processing exception: {input_file}")
                print(str(e))

            self.progress_bar['value'] = index + 1
            self.root.update()
            
            # Force garbage collection after each file
            gc.collect()

        messagebox.showinfo(
            "Complete",
            f"Processing finished!\nSuccess: {success_count}\nFailed: {fail_count}"
        )

        self.clear_list()
        self.btn_start.config(state=tk.NORMAL, text="Start Processing")


if __name__ == "__main__":
    root = tk.Tk()
    app = VRMetadataToolApp(root)
    root.mainloop()
