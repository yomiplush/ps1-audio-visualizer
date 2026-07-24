# PyInstaller hook for glfw — collect native library
from PyInstaller.utils.hooks import collect_dynamic_libs, collect_data_files, collect_all

binaries = collect_dynamic_libs("glfw")
datas = collect_data_files("glfw")
hiddenimports = ["glfw"]

# Also try collect_all for stubborn installs
try:
    tmp_d, tmp_b, tmp_h = collect_all("glfw")
    datas += tmp_d
    binaries += tmp_b
    hiddenimports += tmp_h
except Exception:
    pass
