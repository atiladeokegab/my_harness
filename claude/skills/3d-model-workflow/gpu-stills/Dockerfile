FROM mcr.microsoft.com/playwright/python:v1.48.0-jammy
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libvulkan1 vulkan-tools libegl1 libgl1 libgles2 && rm -rf /var/lib/apt/lists/*
ENV LD_LIBRARY_PATH=/usr/local/nvidia/lib64:/usr/local/nvidia/lib
CMD ["bash", "-c", "bash /out/scripts/run.sh"]
