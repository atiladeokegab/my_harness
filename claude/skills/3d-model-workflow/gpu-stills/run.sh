#!/bin/bash
# Cloud Run GPU task: wire NVIDIA's EGL/Vulkan ICDs, then render one shot.
set -x
ls /usr/local/nvidia/lib64 2>&1 | head -50
nvidia-smi 2>&1 | head -15 || /usr/local/nvidia/bin/nvidia-smi 2>&1 | head -15
mkdir -p /usr/share/glvnd/egl_vendor.d /etc/vulkan/icd.d
echo '{"file_format_version":"1.0.0","ICD":{"library_path":"libEGL_nvidia.so.0"}}' > /usr/share/glvnd/egl_vendor.d/10_nvidia.json
echo '{"file_format_version":"1.0.0","ICD":{"library_path":"libGLX_nvidia.so.0","api_version":"1.3.0"}}' > /etc/vulkan/icd.d/nvidia_icd.json
export LD_LIBRARY_PATH=/usr/local/nvidia/lib64:/usr/local/nvidia/lib:$LD_LIBRARY_PATH
vulkaninfo --summary 2>&1 | grep -i "devicename\|driverName\|apiVersion"
mkdir -p /work
[ "${TOUR:-}" = 1 ] && exec bash /out/scripts/tour-task.sh  # the judge-tour layout check (tour.sh)
cp /out/scripts/render.py /work/ && cd /work && (python3 -c "import playwright" 2>/dev/null || pip install -q playwright==1.48.0) && python3 render.py "${SHOT:-auto}"
