# RenderDoc MCP 工具对比分析

## Linkingooo/renderdoc-mcp vs halby24/RenderDocMCP

---

## 一、项目概览

| 维度 | **Linkingooo/renderdoc-mcp** | **halby24/RenderDocMCP** |
|------|------------------------------|--------------------------|
| 语言 | Python 3.10+ | Python 3.10+ |
| MCP 框架 | FastMCP (mcp[cli]>=1.0.0) | FastMCP 2.0 (fastmcp>=2.0.0) |
| 构建系统 | Hatchling | Hatchling + uv |
| 代码量 | ~5,050 行 (12 个 Python 文件) | ~2,630 行 (19 个 Python 文件) |
| 工具数量 | **42 个 MCP 工具 + 3 个 Prompt 模板** | **15 个 MCP 工具** |
| 许可证 | 未明确 | MIT |
| 版本 | v0.2.0 | 1.0.0 |
| 文档语言 | 中文+英文 | 日文 |
| 已验证平台 | Windows + D3D11/D3D12/Vulkan/GL | Windows + DirectX 11 |

---

## 二、架构对比

### Linkingooo/renderdoc-mcp — **无头直连架构**

```
AI Client (Claude)
    │ stdio (MCP Protocol)
    ▼
MCP Server (Python + FastMCP)
    │ 直接调用 renderdoc Python API
    ▼
renderdoc.pyd / .so (RenderDoc Headless Replay)
```

**特点：**
- 直接加载 RenderDoc 的 Python 模块 (`renderdoc.pyd` / `.so`)
- 无需启动 RenderDoc GUI，纯无头 (headless) 运行
- 通过环境变量 `RENDERDOC_MODULE_PATH` 指定模块路径
- 使用 `rd.InitialiseReplay()` 初始化重放系统
- 单进程架构，无 IPC 开销

### halby24/RenderDocMCP — **GUI 扩展 + IPC 桥接架构**

```
AI Client (Claude)
    │ stdio (MCP Protocol)
    ▼
MCP Server Process (Python + FastMCP 2.0)
    │ File-based IPC (%TEMP%/renderdoc_mcp/)
    ▼
RenderDoc Process (GUI + Extension)
    │ BlockInvoke → ReplayController
    ▼
GPU Replay
```

**特点：**
- MCP Server 和 RenderDoc 是**两个独立进程**
- RenderDoc 扩展通过 `qrenderdoc` 模块注册到 GUI 中
- 使用**文件级 IPC** 通信（JSON 文件 + 锁文件轮询）
  - 原因：RenderDoc 内置 Python 环境没有 `socket` 模块
- 必须先启动 RenderDoc GUI 并手动加载扩展
- 通过 `ctx.Replay().BlockInvoke()` 将操作调度到重放线程

---

## 三、MCP 工具功能对比

### 3.1 通用功能覆盖

| 功能分类 | Linkingooo (42 tools) | halby24 (15 tools) |
|----------|----------------------|-------------------|
| **会话/捕获管理** | open_capture, close_capture, get_capture_info, get_frame_overview | get_capture_status, list_captures, open_capture |
| **事件/DrawCall导航** | list_actions, get_action, set_event, search_actions, find_draws | get_draw_calls, get_draw_call_details, get_frame_summary |
| **反向搜索** | find_draws (按渲染状态) | find_draws_by_shader, find_draws_by_texture, find_draws_by_resource |
| **Pipeline 状态** | get_pipeline_state, get_shader_bindings, get_vertex_inputs, get_draw_call_state | get_pipeline_state |
| **资源管理** | list_textures, list_buffers, list_resources, get_resource_usage | get_texture_info, get_buffer_contents, get_texture_data |
| **数据提取** | save_texture, get_buffer_data, pick_pixel, get_texture_stats, read_texture_pixels, export_draw_textures, save_render_target, export_mesh | get_texture_data, get_buffer_contents |
| **Shader 分析** | disassemble_shader, get_shader_reflection, get_cbuffer_contents | get_shader_info (含反汇编+cbuffer) |
| **高级分析** | pixel_history, get_post_vs_data, diff_draw_calls, analyze_render_passes, sample_pixel_region, debug_shader_at_pixel | ❌ 无 |
| **性能分析** | get_pass_timing, analyze_overdraw, analyze_bandwidth, analyze_state_changes | get_action_timings |
| **诊断工具** | diagnose_negative_values, diagnose_precision_issues, diagnose_reflection_mismatch, diagnose_mobile_risks | ❌ 无 |
| **Prompt 模板** | debug_draw_call, find_rendering_issue, analyze_performance | ❌ 无 |

### 3.2 Linkingooo 独有功能（27 个工具）

**高级调试能力：**
- `pixel_history` — 全帧像素修改历史追踪
- `debug_shader_at_pixel` — 逐像素 Shader 调试，变量追踪
- `diff_draw_calls` — 两个 DrawCall 差异比较，含人类可读的影响分析
- `analyze_render_passes` — 自动检测渲染 Pass 边界（通过 Clear/RT 切换）
- `get_post_vs_data` — 后变换顶点数据
- `sample_pixel_region` — 区域网格采样检测 NaN/Inf/负值/过曝

**数据导出能力：**
- `save_texture` — 支持 PNG/JPG/BMP/TGA/HDR/EXR/DDS 多格式导出
- `export_draw_textures` — 批量导出 DrawCall 绑定的所有贴图
- `save_render_target` — 保存 RT 快照（颜色+深度）
- `export_mesh` — 导出 OBJ 格式网格（含法线和 UV）
- `pick_pixel` — 单像素 RGBA 取值
- `read_texture_pixels` — 矩形区域像素读取（最大 64×64），含异常标记

**性能分析能力：**
- `analyze_overdraw` — 每个 RT 组的 Overdraw 估算
- `analyze_bandwidth` — 写/读带宽估算
- `analyze_state_changes` — 冗余状态切换检测，批处理优化建议

**自动诊断能力：**
- `diagnose_negative_values` — 扫描所有浮点 RT 的负值/NaN/Inf，定位首次引入事件
- `diagnose_precision_issues` — R11G11B10 符号位丢失、深度缓冲精度、SRGB/Linear 不匹配
- `diagnose_reflection_mismatch` — 反射 Pass 与主场景绘制的差异分析
- `diagnose_mobile_risks` — 移动端 GPU 特定风险评估（Adreno/Mali/PowerVR/Apple）

### 3.3 halby24 独有功能

- `list_captures` — 列出指定目录下的 .rdc 文件（Linkingooo 不提供文件浏览）
- `find_draws_by_shader` — 按 Shader 名称反向查找 DrawCall
- `find_draws_by_texture` — 按贴图名称反向查找 DrawCall
- `find_draws_by_resource` — 按资源 ID 精确反向查找 DrawCall
- `get_frame_summary` — 帧级统计概要（Linkingooo 通过 `get_frame_overview` 提供类似功能）

---

## 四、设计理念对比

### Linkingooo/renderdoc-mcp — "LLM 优先"设计

1. **人类可读输出**：所有枚举值转为可读文本（"SrcAlpha" 而非 "6"），blend 公式生成文字描述
2. **自动异常检测**：工具自动标记 NaN / Inf / 负值 / 极端值
3. **操作链引导**：每个工具的输出包含 ID 和后续操作建议
4. **Token 预算控制**：大数据工具支持过滤和摘要模式
5. **GPU Quirk 智能**：自动检测 GPU 型号并给出特定警告（Adreno mediump 精度、Mali discard+early-Z 等）
6. **一次调用分析**：`get_draw_call_state` 在单次调用中返回完整绘制状态（含贴图尺寸/格式/RT/Shader 全貌）
7. **Prompt 模板**：内置 3 个引导式分析模板，降低 AI 使用门槛

### halby24/RenderDocMCP — "忠实桥接"设计

1. **API 直通**：工具输出忠实反映 RenderDoc API 的原始数据结构
2. **原始数据格式**：贴图/缓冲数据以 Base64 编码返回
3. **结构化分层**：服务层清晰分离（Facade → Service → Serializer）
4. **反向搜索便利**：提供按 Shader/Texture/Resource 名称反查 DrawCall 的专用工具
5. **GUI 集成**：通过 RenderDoc 扩展机制注册菜单项，可在 GUI 中查看 Bridge 状态
6. **轻量实现**：专注核心功能，代码量小，易于理解和维护

---

## 五、优劣势分析

### Linkingooo/renderdoc-mcp

**优势：**
- ✅ **功能极其丰富**：42 个工具覆盖从基础查询到高级调试的完整流程
- ✅ **无头运行**：无需 GUI，适合 CI/CD 和自动化场景
- ✅ **AI 友好**：输出经过精心设计，便于 LLM 理解和使用
- ✅ **诊断自动化**：内置精度问题、移动端兼容性等高级诊断
- ✅ **跨平台**：支持 Windows/Linux/macOS，pyd + so 均可
- ✅ **性能分析**：Overdraw、带宽、状态切换等深度分析能力
- ✅ **Prompt 模板**：降低 AI 理解和使用复杂工作流的门槛

**劣势：**
- ❌ 无法与 RenderDoc GUI 交互（纯无头模式）
- ❌ 代码量大，维护成本更高
- ❌ 无法在已打开 GUI 的 RenderDoc 实例上操作
- ❌ 未提供文件系统浏览（list_captures）
- ❌ 部分高级功能复杂度高，可能在特殊场景下有稳定性风险

### halby24/RenderDocMCP

**优势：**
- ✅ **GUI 集成**：直接操作已打开的 RenderDoc 窗口，所见即所得
- ✅ **实时同步**：AI 分析的数据与 GUI 显示的完全一致
- ✅ **代码精简**：~2,600 行代码，易于理解、调试和贡献
- ✅ **反向搜索**：专用工具按 Shader/Texture/Resource 名称反查
- ✅ **文件浏览**：list_captures 列出目录下的捕获文件
- ✅ **GPU 计时**：直接使用 GPU 计数器获取真实 Timing 数据
- ✅ **架构清晰**：Facade + Service + Serializer 分层明确

**劣势：**
- ❌ **必须依赖 GUI**：无法无头运行，不适合自动化流水线
- ❌ **功能有限**：仅 15 个工具，缺少像素历史、Shader 调试、Overdraw 分析等高级能力
- ❌ **IPC 性能开销**：文件轮询 IPC 引入延迟（50ms 轮询间隔 + 30s 超时）
- ❌ **仅验证 Windows + D3D11**：跨平台 / 跨 API 支持未知
- ❌ **输出原始**：枚举值等未做人类可读转换，LLM 理解成本更高
- ❌ **无诊断/分析工具**：缺少自动化诊断和渲染分析能力
- ❌ **无 Prompt 模板**：AI 需要自行编排工具使用流程

---

## 六、适用场景建议

| 场景 | 推荐方案 |
|------|---------|
| AI 辅助图形 Bug 定位与修复 | **Linkingooo** — 丰富的诊断和分析工具链 |
| CI/CD 自动化渲染测试 | **Linkingooo** — 无头运行，可集成到自动化流水线 |
| 交互式图形调试（GUI 同步） | **halby24** — GUI 集成，所见即所得 |
| 快速原型/学习 RenderDoc MCP 开发 | **halby24** — 代码简洁，架构清晰 |
| 移动端渲染问题排查 | **Linkingooo** — GPU Quirk 检测和移动端风险诊断 |
| 性能优化分析 | **Linkingooo** — Overdraw/带宽/状态切换分析 |
| 轻量级查询已打开的捕获 | **halby24** — 直接桥接 GUI 数据 |
| 深度 Shader 调试 | **Linkingooo** — 像素历史、Shader 单步、变量追踪 |

---

## 七、总结

**Linkingooo/renderdoc-mcp** 是一个**功能全面、AI 优先设计**的工具，覆盖从基础查询到高级诊断的完整图形调试流程，适合需要深度分析和自动化的专业场景。

**halby24/RenderDocMCP** 是一个**轻量、实用的 GUI 桥接方案**，让 AI 能直接与已打开的 RenderDoc 实例交互，适合交互式调试和快速查询场景。

两者在架构上互补：Linkingooo 走"无头重放 + AI 智能"路线，halby24 走"GUI 扩展 + 忠实桥接"路线。选择取决于具体使用场景——需要深度分析选 Linkingooo，需要 GUI 交互选 halby24。
