# wechat_stream_ocr

## 项目目标

本项目用于持续接收微信聊天窗口截图流，检测聊天内容是否有新增消息，并在有新增时调用 OCR 提取文本消息，最终以结构化文本形式通过 ZeroMQ `PUB` 模式发布出去。

该项目面向固定场景：

- 截图来源为微信聊天窗口
- 聊天窗口尺寸固定
- 截图频率固定
- 输入方式为 WebSocket 持续推送图片
- 推送频率约为每 `500ms` 一张

## 核心流程

1. 服务端通过 WebSocket 持续接收聊天窗口截图。
2. 每次收到新截图后，与上一张截图进行差分比较。
3. 如果判断为“无新消息产生”，则直接忽略本次截图。
4. 如果判断为“有新消息产生”，则调用 OCR 模块识别新增聊天记录。
5. 从 OCR 结果中提取并拼接为统一文本格式：`发送人 + 时间 + 内容`。
6. 忽略所有表情、图片、贴图、非文字消息。
7. 将最终文本结果通过 ZeroMQ `PUB` 发布给下游消费者。

## 功能需求

### 1. WebSocket 图片接收

- 系统必须提供一个 WebSocket 服务端接口。
- WebSocket 连接建立后，客户端持续推送微信聊天窗口截图。
- 截图格式建议支持 `JPEG`、`PNG`，也可扩展为 Base64 或二进制帧。
- 系统应能够稳定处理约 `500ms/张` 的输入频率。
- 系统应保存最近一张有效截图，作为下一次差分比较的基准图。

### 2. 截图差分检测

- 每次收到截图后，必须与上一张截图进行比较。
- 差分逻辑目标不是判断“画面有任何变化”，而是判断“是否出现新的聊天记录”。
- 应优先关注聊天内容区域，避免窗口边框、滚动条、头像闪动、光标闪烁等无关变化造成误判。
- 若差分结果表明没有新增消息，则本次流程直接结束，不调用 OCR。
- 若差分结果表明存在新增消息，则进入 OCR 识别流程。

### 3. OCR 文本识别

- 仅在检测到新增消息时调用 OCR，避免无效识别开销。
- OCR 目标为聊天窗口中的文字消息内容。
- 需要识别以下信息：
  - 发消息的人
  - 消息时间
  - 消息正文
- OCR 应尽可能只处理新增区域，减少重复识别。
- 对于历史消息重复出现的情况，应尽量去重，避免重复发布。

### 4. 消息过滤规则

- 只保留文字类型消息。
- 忽略以下内容：
  - 表情
  - 图片
  - 贴图
  - 非文字卡片类内容
  - 无法稳定识别的装饰性 UI 元素
- 若单条消息中同时包含文字和表情，应仅保留文字部分。
- 若无法识别发送人或时间，可先保留空值或使用占位字段，但需要保证输出结构一致。

### 5. 输出格式

- OCR 结果需要统一拼接为文本结构。
- 基础输出格式定义为：

```text
发送人 + 时间 + 内容
```

- 建议标准化为如下格式：

```text
[发送人] [时间] 内容
```

- 示例：

```text
[张三] [2026-03-29 13:45:00] 今天下午开会
```

- 一次检测到多条新增消息时，应按聊天出现顺序逐条输出。

### 6. ZeroMQ 发布

- 系统必须提供 ZeroMQ `PUB` 输出能力。
- 每条新增文本消息都应发布到指定主题或默认主题。
- 发布内容建议为 UTF-8 文本，后续也可扩展为 JSON。
- 下游订阅方通过 ZeroMQ `SUB` 接收消息。
- 系统应保证：
  - 有新增消息才发布
  - 无新增消息不发布
  - 同一条消息尽量不重复发布

## 非功能需求

### 性能

- 在 `500ms/张` 的输入频率下，应尽量保证处理链路无明显积压。
- 差分检测应轻量化，OCR 调用应尽量只在必要时触发。
- 系统应尽量支持连续长时间运行。

### 稳定性

- WebSocket 断连后应允许客户端重连。
- 对异常图片、空帧、损坏图片应具备容错能力，不能导致服务崩溃。
- OCR 失败时应记录错误并跳过当前帧，不影响后续处理。

### 可维护性

- 差分检测、OCR、消息过滤、ZMQ 发布应分模块实现。
- 日志中应能区分以下状态：
  - 收到图片
  - 无新增消息
  - 检测到新增消息
  - OCR 成功/失败
  - ZMQ 发布成功/失败

## 建议模块划分

- `ws_server`
  - 接收 WebSocket 图片流
- `frame_store`
  - 保存上一帧、当前帧及必要的状态
- `diff_detector`
  - 判断是否有新增聊天记录
- `ocr_engine`
  - 执行文字识别
- `message_parser`
  - 提取发送人、时间、内容
- `message_filter`
  - 过滤表情、图片、非文字内容
- `publisher_zmq`
  - 通过 ZeroMQ `PUB` 输出结果

## 建议数据流

```text
WebSocket 图片输入
    ->
保存当前帧
    ->
与上一帧做差分
    ->
无新增 -> 丢弃
    ->
有新增 -> OCR
    ->
提取 发送人/时间/内容
    ->
过滤表情和图片
    ->
格式化文本
    ->
ZeroMQ PUB 发布
```

## 待确认项

以下内容建议在开发前进一步明确：

- WebSocket 输入到底使用二进制帧还是 Base64 文本帧
- 微信聊天窗口中“时间”是否总是可见，还是需要按规则补全
- 发送人字段是否总能从 UI 中直接识别
- 输出是纯文本还是 JSON
- ZeroMQ 的发布地址、端口、topic 命名规则
- 差分检测区域是否只限定在聊天内容主体区域
- 是否需要消息去重缓存，防止重复截图导致重复发布

## 第一版开发范围

建议第一版只实现最小闭环：

- WebSocket 接收截图
- 保存上一帧与当前帧
- 基于聊天区域做差分判断
- 有新增时调用 OCR
- 提取 `发送人 + 时间 + 内容`
- 过滤表情和图片
- 通过 ZeroMQ `PUB` 输出文本

以上功能跑通后，再继续优化：

- 更精确的新增区域检测
- 更稳健的消息去重
- 更高质量的 OCR 清洗
- JSON 输出格式
- 监控和日志完善

## 当前 Python 骨架

仓库当前已经提供第一版 Python 项目骨架，目标是先跑通以下最小链路：

- WebSocket 接收截图
- 保存上一帧并做差分
- 检测到变化时触发 OCR 接口
- 清洗文本消息
- 通过 ZeroMQ `PUB` 发布

### 项目结构

```text
.
├── README.md
├── pyproject.toml
└── src/
    └── wechat_stream_ocr/
        ├── config.py
        ├── diff_detector.py
        ├── frame_store.py
        ├── main.py
        ├── message_filter.py
        ├── message_parser.py
        ├── models.py
        ├── ocr.py
        ├── pipeline.py
        ├── publisher_zmq.py
        └── ws_server.py
```

### 模块说明

- `config.py`
  - 统一管理 WebSocket、差分阈值、OCR backend、ZMQ 地址等配置
- `ws_server.py`
  - 提供 WebSocket 服务端，支持二进制图片帧和 JSON Base64 文本帧
- `frame_store.py`
  - 保存上一帧截图
- `diff_detector.py`
  - 对聊天区域做差分，判断是否出现新消息
- `ocr.py`
  - OCR 抽象层，默认是 `stub`，可切换到 `paddleocr`
  - `paddleocr` 路径按 `PaddleOCR 3.x` 接口实现
- `message_parser.py`
  - 将 OCR 文本行解析为 `发送人 + 时间 + 内容`
- `message_filter.py`
  - 过滤表情占位符、图片占位符和纯非文本内容
- `publisher_zmq.py`
  - 通过 ZeroMQ `PUB` 发布文本
- `pipeline.py`
  - 串联整条处理链
- `main.py`
  - 程序入口

## 安装

建议使用 Python `3.11+`。

```bash
./scripts/install.sh
```

这个脚本会在项目目录创建 `.venv`，并把项目依赖和 OCR 依赖安装到虚拟环境中，不依赖 `sudo`。默认行为是：

- 如果当前 `PYTHON_BIN` 低于 `3.11`，脚本会自动从镜像安装用户态 `Miniconda3`，并改用其中的 `python`
- 检测到可安全匹配的 GPU 环境时优先安装 GPU 版 Paddle
- 否则自动回退安装 CPU 版 Paddle
- 如果宿主机 `python3` 没有 `pip`，脚本会先尝试 `ensurepip --user`，再自动使用镜像 `get-pip.py` 补齐用户态 `pip`
- 如果目标机缺少 `python3-venv/ensurepip`，脚本会自动尝试 `python3 -m pip install --user virtualenv` 再创建 `.venv`
- 如果 `.venv` 已经存在但里面没有 `pip`，脚本会先尝试 `ensurepip` 补齐；失败时会回退为用户态 `virtualenv` 重建
- `pip install` 默认使用镜像源
- 使用项目内的 `npm install` 安装本地 `pm2`
- 通过 `npx pm2 install pm2-logrotate` 配置日志轮转，不依赖全局安装和 `root`

也可以显式指定：

```bash
./scripts/install.sh auto
./scripts/install.sh cpu
./scripts/install.sh gpu
```

内部大致等价于：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip setuptools wheel
.venv/bin/python -m pip install -e .
.venv/bin/python -m pip install paddlepaddle paddleocr "paddlex[ocr]"
npm install
PM2_HOME=./run/.pm2 npx pm2 install pm2-logrotate
PM2_HOME=./run/.pm2 npx pm2 set pm2-logrotate:retain 1
PM2_HOME=./run/.pm2 npx pm2 set pm2-logrotate:rotateInterval '0 0 * * *'
```

如果标准库 `venv` 不可用，安装脚本会自动退化为：

```bash
python3 -m pip install --user virtualenv
python3 -m virtualenv .venv
```

默认会用阿里云镜像补宿主机 `pip`，也可以通过环境变量覆盖：

```bash
export GET_PIP_URL=https://mirrors.aliyun.com/pypi/get-pip.py
export PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple
export PIP_TRUSTED_HOST=mirrors.aliyun.com
```

如果当前机器没有可用的 Python `3.11+`，脚本默认会从清华镜像安装用户态 `Miniconda3`：

```bash
export MINICONDA_DIR="$HOME/.local/miniconda3"
export MINICONDA_MIRROR_BASE_URL=https://mirrors.tuna.tsinghua.edu.cn/anaconda/miniconda
```

## 运行

默认通过脚本启动，本地 `pm2` 状态保存在 `run/.pm2`，应用日志保存在 `run/logs/`：

- WebSocket 地址：`ws://0.0.0.0:8765`
- ZeroMQ `PUB` 地址：`tcp://127.0.0.1:5556`
- ZeroMQ topic：`wechat.chat`
- OCR backend：`paddleocr`
- Paddle device：`auto`

启动命令：

```bash
./scripts/start.sh
```

停止服务：

```bash
./scripts/stop.sh
```

查看日志：

```bash
./scripts/logs.sh
```

底层等价于：

```bash
PM2_HOME=./run/.pm2 npx pm2 startOrRestart ecosystem.config.js --only wechat-stream-ocr --update-env
PM2_HOME=./run/.pm2 npx pm2 logs wechat-stream-ocr
PM2_HOME=./run/.pm2 npx pm2 delete wechat-stream-ocr
```

日志轮转策略：

- 使用 `pm2-logrotate`
- 每天 `00:00` 强制轮转一次
- `retain=1`，只保留 1 份已轮转日志
- `compress=true`，已轮转日志会压缩
- `max_size=10M`，单个活跃日志超过阈值也会提前轮转

注意：`pm2-logrotate` 的保留语义是“保留多少个已轮转文件”，不是精确按日志年龄删除。
当前配置的实际效果是：始终保留当前正在写入的日志文件，以及最多 1 份历史轮转文件。配合每日午夜轮转，通常就是“今天的当前日志 + 昨天的归档日志”。

如果要临时覆盖监听地址或日志级别，可以在启动前设置环境变量：

```bash
export WSOCR_WS_HOST=0.0.0.0
export WSOCR_WS_PORT=8765
export WSOCR_LOG_LEVEL=INFO
./scripts/start.sh
```

## 环境变量

支持通过环境变量覆盖默认配置：

```bash
export WSOCR_WS_HOST=0.0.0.0
export WSOCR_WS_PORT=8765
export WSOCR_ZMQ_BIND=tcp://127.0.0.1:5556
export WSOCR_ZMQ_TOPIC=wechat.chat
export WSOCR_OCR_BACKEND=paddleocr
export WSOCR_MOCK_OCR_LINES='[张三] [2026-03-30 13:45:00] 今天下午开会'
export WSOCR_OCR_LANGUAGE=ch
export WSOCR_OCR_MIN_CONFIDENCE=0.60
export WSOCR_PADDLE_DEVICE=auto
export WSOCR_PADDLE_TEXT_DETECTION_MODEL_NAME=
export WSOCR_PADDLE_TEXT_RECOGNITION_MODEL_NAME=
export WSOCR_PADDLE_CPU_TEXT_DETECTION_MODEL_NAME=PP-OCRv5_mobile_det
export WSOCR_PADDLE_CPU_TEXT_RECOGNITION_MODEL_NAME=PP-OCRv5_mobile_rec
export WSOCR_PADDLE_GPU_TEXT_DETECTION_MODEL_NAME=PP-OCRv5_server_det
export WSOCR_PADDLE_GPU_TEXT_RECOGNITION_MODEL_NAME=PP-OCRv5_server_rec
export WSOCR_PADDLE_USE_DOC_ORIENTATION_CLASSIFY=false
export WSOCR_PADDLE_USE_DOC_UNWARPING=false
export WSOCR_PADDLE_USE_TEXTLINE_ORIENTATION=false
export WSOCR_PADDLE_ENABLE_MKLDNN=false
export WSOCR_PADDLE_ENABLE_HPI=false
export WSOCR_PADDLE_CPU_THREADS=1
export WSOCR_LOG_LEVEL=INFO
```

设备和模型选择规则：

- 默认 `WSOCR_PADDLE_DEVICE=auto`
- `auto` 模式下，运行时会优先检查 `nvidia-smi` 和 Paddle CUDA 能力
- 如果 GPU 可用，则默认使用更高质量的 GPU 模型
- 如果 GPU 不可用，则自动回退到 CPU，并默认使用轻量 CPU 模型
- 如果显式设置 `WSOCR_PADDLE_DEVICE=gpu`，但运行时 GPU 不可用，则会直接报错
- 如果显式设置 `WSOCR_PADDLE_TEXT_DETECTION_MODEL_NAME` 和 `WSOCR_PADDLE_TEXT_RECOGNITION_MODEL_NAME`，则优先使用你手动指定的模型

差分相关配置：

```bash
export WSOCR_DIFF_PIXEL_THRESHOLD=18
export WSOCR_DIFF_MIN_CHANGED_RATIO=0.003
export WSOCR_DIFF_MIN_MEAN_DELTA=1.5
export WSOCR_ROI_LEFT=0.08
export WSOCR_ROI_TOP=0.10
export WSOCR_ROI_RIGHT=0.94
export WSOCR_ROI_BOTTOM=0.82
```

## WebSocket 输入格式

### 1. 二进制帧

- 直接发送 `PNG/JPEG` 二进制图片数据

### 2. JSON 文本帧

```json
{
  "source": "capture-agent",
  "message_id": "frame-000001",
  "image_base64": "iVBORw0KGgoAAA..."
}
```

也支持：

- `image`
- `data`

这三个字段名中的任意一个作为 Base64 图片内容。

### 3. Data URI

以下格式也支持：

```text
data:image/png;base64,iVBORw0KGgoAAA...
```

## 当前实现说明

- 默认 OCR backend 为 `stub`
  - 这意味着服务可以跑起来，但不会真正识别截图文字
- 现在已经接入真实 `paddleocr` backend
  - 启动时指定 `--ocr-backend paddleocr` 或设置 `WSOCR_OCR_BACKEND=paddleocr`
  - OCR 默认只识别聊天 ROI，而不是整张窗口
  - OCR 结果会按版面位置排序，并按最小置信度过滤
- 第一版差分基于固定聊天 ROI 和像素变化比例判断
- 当前解析器会优先识别如下格式：

```text
[张三] [2026-03-29 13:45:00] 今天下午开会
张三 13:45 今天下午开会
张三 2026-03-29 13:45:00 今天下午开会
```

- 如果 OCR 返回的文本还不够规整，后续需要继续针对微信界面做专门规则优化

## 后续建议

在这个骨架基础上，下一步优先做这几件事：

- 用真实微信截图样本调 ROI 和差分阈值
- 接入真实 OCR backend，并只识别新增区域
- 针对微信消息气泡布局补充更稳定的发送人/时间提取规则
- 增加端到端测试样本
