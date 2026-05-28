import os
import struct
import subprocess
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import threading
import gc

# ==========================================
# VR180 Metadata Constants (Google Spatial Media Standard)
# ==========================================
VR_UUID = b'\xff\xcc\x82\x63\xf8\x55\x4a\x93\x88\x14\x58\x7a\x02\x52\x1f\xdd'

VR_XML = (
    b'<?xml version="1.0"?>'
    b'<rdf:SphericalVideo '
    b'xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" '
    b'xmlns:gspherical="http://ns.google.com/videos/1.0/spherical/">'
    b'<gspherical:Spherical>true</gspherical:Spherical>'
    b'<gspherical:Stitched>true</gspherical:Stitched>'
    b'<gspherical:StitchingSoftware>VR180 Metadata Injector</gspherical:StitchingSoftware>'
    b'<gspherical:ProjectionType>equirectangular</gspherical:ProjectionType>'
    b'<gspherical:StereoMode>left-right</gspherical:StereoMode>'
    b'</rdf:SphericalVideo>'
)

CHUNK_SIZE = 8 * 1024 * 1024  # 8MB Streaming Buffer

def strip_old_metadata(input_file, output_file):
    """Use FFmpeg to strip old metadata to prevent conflicts."""
    cmd = [
        'ffmpeg', '-y', '-i', input_file,
        '-c', 'copy', '-map_metadata', '-1',
        output_file
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def inject_vr_metadata_streaming(input_file, output_file, progress_callback):
    """Inject VR180 metadata using streaming to handle huge files."""
    file_size = os.path.getsize(input_file)
    processed_size = 0

    with open(input_file, 'rb') as f_in, open(output_file, 'wb') as f_out:
        while True:
            header = f_in.read(8)
            if not header:
                break
            
            box_size, box_type = struct.unpack('>I4s', header)
            
            if box_size == 1:
                ext_size_data = f_in.read(8)
                box_size = struct.unpack('>Q', ext_size_data)[0]
                header += ext_size_data
            
            if box_type == b'moov':
                moov_data = f_in.read(box_size - len(header))
                
                uuid_box_data = VR_UUID + VR_XML
                uuid_box_size = len(uuid_box_data) + 8
                uuid_box = struct.pack('>I4s', uuid_box_size, b'uuid') + uuid_box_data
                
                new_moov_size = box_size + uuid_box_size
                new_header = struct.pack('>I4s', new_moov_size, b'moov')
                
                f_out.write(new_header)
                f_out.write(moov_data)
                f_out.write(uuid_box)
                
                processed_size += box_size
            else:
                f_out.write(header)
                bytes_to_copy = box_size - len(header)
                
                while bytes_to_copy > 0:
                    chunk = f_in.read(min(CHUNK_SIZE, bytes_to_copy))
                    if not chunk:
                        break
                    f_out.write(chunk)
                    bytes_to_copy -= len(chunk)
                    
                    processed_size += len(chunk)
                    if progress_callback:
                        progress_callback(processed_size / file_size * 100)
                    
        gc.collect()

class VRMetadataApp:
    def __init__(self, root):
        self.root = root
        self.root.title("VR180 Metadata Tool")
        self.root.geometry("600x450")
        
        # --- Section 1: Select Specific Files (Single/Multiple) ---
        self.frame_files = tk.LabelFrame(root, text=" Option 1: Select Specific Files (Single or Multiple) ", padx=10, pady=10)
        self.frame_files.pack(fill="x", padx=20, pady=10)
        
        self.btn_inject_files = tk.Button(self.frame_files, text="Select Files -> INJECT VR180", 
                                          command=lambda: self.start_process(mode="inject", source="files"), bg="#4CAF50", fg="black")
        self.btn_inject_files.pack(side="left", padx=10, expand=True, fill="x")
        
        self.btn_clear_files = tk.Button(self.frame_files, text="Select Files -> CLEAR Metadata", 
                                         command=lambda: self.start_process(mode="clear", source="files"))
        self.btn_clear_files.pack(side="right", padx=10, expand=True, fill="x")

        # --- Section 2: Select Entire Folder ---
        self.frame_folder = tk.LabelFrame(root, text=" Option 2: Select Entire Folder (Batch All MP4s) ", padx=10, pady=10)
        self.frame_folder.pack(fill="x", padx=20, pady=10)
        
        self.btn_inject_folder = tk.Button(self.frame_folder, text="Select Folder -> INJECT VR180", 
                                           command=lambda: self.start_process(mode="inject", source="folder"), bg="#4CAF50", fg="black")
        self.btn_inject_folder.pack(side="left", padx=10, expand=True, fill="x")
        
        self.btn_clear_folder = tk.Button(self.frame_folder, text="Select Folder -> CLEAR Metadata", 
                                          command=lambda: self.start_process(mode="clear", source="folder"))
        self.btn_clear_folder.pack(side="right", padx=10, expand=True, fill="x")

        # --- Progress UI ---
        self.file_label = tk.Label(root, text="Current File: None", fg="blue")
        self.file_label.pack(pady=5)
        
        self.progress = ttk.Progressbar(root, orient="horizontal", length=500, mode="determinate")
        self.progress.pack(pady=5)
        
        self.status_var = tk.StringVar()
        self.status_var.set("Ready")
        self.status_label = tk.Label(root, textvariable=self.status_var)
        self.status_label.pack(pady=5)

    def update_progress(self, percent):
        self.progress['value'] = percent
        self.root.update_idletasks()

    def toggle_buttons(self, state):
        self.btn_inject_files.config(state=state)
        self.btn_clear_files.config(state=state)
        self.btn_inject_folder.config(state=state)
        self.btn_clear_folder.config(state=state)

    def process_thread(self, file_paths, mode):
        try:
            total_files = len(file_paths)
            
            for index, input_path in enumerate(file_paths):
                filename = os.path.basename(input_path)
                folder_path = os.path.dirname(input_path)
                
                self.file_label.config(text=f"Processing ({index+1}/{total_files}): {filename}")
                
                if mode == "inject":
                    output_path = os.path.join(folder_path, filename.rsplit('.', 1)[0] + '_injected.mp4')
                    temp_path = os.path.join(folder_path, filename.rsplit('.', 1)[0] + '_temp.mp4')
                    
                    self.status_var.set("Step 1/2: Cleaning old metadata (FFmpeg)...")
                    strip_old_metadata(input_path, temp_path)
                    
                    self.status_var.set("Step 2/2: Injecting VR180 metadata (Streaming)...")
                    inject_vr_metadata_streaming(temp_path, output_path, self.update_progress)
                    
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
                        
                elif mode == "clear":
                    output_path = os.path.join(folder_path, filename.rsplit('.', 1)[0] + '_cleared.mp4')
                    self.status_var.set("Clearing all metadata (FFmpeg)...")
                    
                    self.update_progress(50)
                    strip_old_metadata(input_path, output_path)
                    self.update_progress(100)
                    
            self.status_var.set(f"Done! Successfully processed {total_files} files.")
            self.file_label.config(text="All files processed.")
            messagebox.showinfo("Success", f"Processing complete!\n{total_files} files processed.")
            
        except Exception as e:
            self.status_var.set("Error occurred.")
            messagebox.showerror("Error", str(e))
        finally:
            self.toggle_buttons(tk.NORMAL)
            self.progress['value'] = 0

    def start_process(self, mode, source):
        file_paths = []
        
        if source == "files":
            # Allow multi-selection of specific files
            selected = filedialog.askopenfilenames(filetypes=[("MP4 Files", "*.mp4")])
            if not selected:
                return
            file_paths = list(selected)
            
        elif source == "folder":
            # Select directory and filter MP4 files
            folder_path = filedialog.askdirectory()
            if not folder_path:
                return
            
            file_paths = [os.path.join(folder_path, f) for f in os.listdir(folder_path) 
                          if f.lower().endswith('.mp4') and not f.endswith('_injected.mp4') and not f.endswith('_cleared.mp4')]
            
            if not file_paths:
                messagebox.showinfo("Info", "No valid MP4 files found in the selected folder.")
                return

        self.toggle_buttons(tk.DISABLED)
        self.progress['value'] = 0
        
        threading.Thread(target=self.process_thread, args=(file_paths, mode), daemon=True).start()

if __name__ == "__main__":
    root = tk.Tk()
    app = VRMetadataApp(root)
    root.mainloop()