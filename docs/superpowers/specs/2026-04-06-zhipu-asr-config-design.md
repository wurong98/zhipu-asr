# Zhipu ASR 输入法 — 配置文件支持

**日期:** 2026-04-06

**状态:** 已批准

---

## 目标

为 ASR CLI 添加 YAML 配置文件支持，通过 `hotwords` 和 `prompt` 参数提升识别效果。

---

## 配置方案

**配置文件路径：**
- 默认：`./config.yaml`（当前目录）
- 自定义：`--config <path>` 命令行指定

**config.yaml 格式：**
```yaml
hotwords:
  - 人名
  - 地名
  - 专业术语

prompt: "上下文提示文字"
```

**命令行：**
```bash
python asr_cli.py --config custom.yaml
python asr_cli.py  # 使用默认 config.yaml
```

---

## 实现

- 新增 `_load_config(yaml_path)` 方法
- `_transcribe()` 添加 `hotwords` 和 `prompt` 参数
- 配置为可选，不存在时优雅降级

---

## 文件变更

- `asr_cli.py` — 添加配置读取逻辑
