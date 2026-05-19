# 部署方法

## 1. 本机部署

适合现在这台电脑使用，视频生成速度和稳定性最好。

### 环境要求

- Windows 10/11
- Python 3.10 或更高版本
- FFmpeg，并确保 `ffmpeg` 和 `ffprobe` 可以在命令行里直接运行
- 网络可访问公开数据源和 Edge TTS

### 安装依赖

```powershell
cd D:\etf
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 启动网页端

```powershell
python -m uvicorn server:app --host 127.0.0.1 --port 8765
```

浏览器打开：

```text
http://127.0.0.1:8765/index.html
```

### 生成正式视频

```powershell
python render_csi300_series.py
```

结果在：

```text
runs/csi300_series_时间戳/
```

## 2. 局域网部署

如果要让同一局域网里的其他设备访问网页，把启动命令改成：

```powershell
python -m uvicorn server:app --host 0.0.0.0 --port 8765
```

然后在其他设备访问：

```text
http://本机局域网IP:8765/index.html
```

注意：生成视频会占用本机 CPU、内存和磁盘，建议只在可信局域网使用。

## 3. 云服务器部署

适合只部署网页端和轻量测试视频。正式批量视频生成更建议留在本机，因为需要 FFmpeg、字体、TTS、公开数据下载和较多磁盘空间。

### Linux 服务器准备

```bash
sudo apt update
sudo apt install -y python3 python3-venv ffmpeg fonts-noto-cjk
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 启动服务

```bash
python -m uvicorn server:app --host 0.0.0.0 --port 8765
```

### 后台运行示例

```bash
nohup python -m uvicorn server:app --host 0.0.0.0 --port 8765 > app.log 2>&1 &
```

## 4. GitHub 上传方法

如果本机装了 GitHub CLI，并已登录：

```powershell
gh auth login
gh repo create index-video-studio --private --source . --remote origin --push
```

如果想公开仓库，把 `--private` 改成 `--public`。

如果不用 GitHub CLI：

1. 在 GitHub 新建空仓库，名字建议 `index-video-studio`。
2. 复制仓库地址。
3. 在本地执行：

```powershell
git remote add origin https://github.com/你的用户名/index-video-studio.git
git branch -M main
git push -u origin main
```

## 5. 生产注意事项

- `runs/` 是生成产物目录，不建议提交到 GitHub。
- 每次发布视频前，应人工复核数据来源、字幕、画面和风险提示。
- 视频里不写具体日期，追溯日期放在 `manifest.json`。
- 公共服务器上不要开放任意文件上传给陌生人使用。
