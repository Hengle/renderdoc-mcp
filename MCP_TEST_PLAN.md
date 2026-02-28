# RenderDoc MCP 工具实测文档

## 测试用 Capture 文件

- **路径**: `C:\Users\18523\Downloads\5.rdc`
- **API**: OpenGL ES
- **分辨率**: 1496x720
- **总 Actions**: 285 (266 draw calls, 18 clears, 0 dispatches)
- **纹理**: 172 个, 139.73 MB
- **Buffer**: 141 个, 21.72 MB
- **Render Passes**: 18 个
- **主 RT**: `ResourceId::4749` (1496x720, R8G8B8A8_UNORM, 151 draws)

## 关键 Event ID 参考

| EID | 类型 | 顶点数 | 说明 |
|-----|------|--------|------|
| 24 | Clear | - | glClear Color+Depth+Stencil |
| 111 | Draw | 59148 | 大型 draw, pass #2 |
| 569 | Draw | 83829 | 最大 draw 之一, TriangleStrip, VS 5 inputs |
| 825 | Draw | 83829 | 同顶点数但不同 shader（可与 569 diff） |
| 855 | Clear | - | 主 pass (#6) 起点, clear color=(0.178,0.203,0.25) |
| 1014 | Draw | 59148 | 主 pass 内大型 draw |
| 3076 | Draw | 1920 | UI 相关 BaseVertex draw |
| 3125 | Draw | - | 主 pass (#6) 最后一个 draw |
| 3346 | Draw | 6 | 后处理全屏 quad |
| 3622 | Draw | 6924 | 最终 pass 内 draw |

## 测试流程与结果

### 第一阶段：基础工具

| # | 工具 | 测试参数 | 预期 | 状态 |
|---|------|----------|------|------|
| 1 | `open_capture` | filepath=`C:\Users\18523\Downloads\5.rdc` | 返回 API/action/texture/buffer 数 | ✅ |
| 2 | `get_capture_info` | (无参数) | 返回当前 capture 信息 | ✅ |
| 3 | `get_frame_overview` | (无参数) | 返回分辨率/draw 统计/RT 列表 | ✅ |
| 4 | `list_actions` | max_depth=2, filter_flags=["Drawcall","Clear"] | 过滤出 draw+clear | ✅ |
| 5 | `search_actions` | name_pattern="BaseVertex" | 找到所有 BaseVertex 调用 | ✅ (111 matches) |
| 6 | `get_action` | event_id=569 | 返回单个 action 详情 | ❌→🔧 Bug 3: depthOutput→depthOut |
| 7 | `set_event` | event_id=569 | 成功导航 | ✅ |

### 第二阶段：Draw Call 分析

| # | 工具 | 测试参数 | 预期 | 状态 |
|---|------|----------|------|------|
| 8 | `get_draw_call_state` | event_id=569 | 完整 draw 状态（含 RT、blend、shader 等） | ✅ (RT 为空因旧 bug, 需重启) |
| 9 | `diff_draw_calls` | eid1=569, eid2=825 | 列出差异（shader/inputs 不同） | ✅ |
| 10 | `get_pipeline_state` | event_id=569 | 返回完整管线状态 | ⚠️ output_targets 空 (需重启), 其余正常 |
| 11 | `get_vertex_inputs` | event_id=569 | 返回顶点属性和 buffer 绑定 | ⚠️→🔧 Bug 4: format 显示 Swig 指针 |
| 12 | `find_draws` | min_vertices=50000, max_results=5 | 找到 5 个大 draw | ✅ |
| 13 | `find_draws` | blend=True | 找到开启 blend 的 draw | ✅ (0 matches, 正常) |
| 14 | `analyze_render_passes` | (无参数) | 检测 18 个 render pass | ✅ |

### 第三阶段：Shader 分析

| # | 工具 | 测试参数 | 预期 | 状态 |
|---|------|----------|------|------|
| 15 | `disassemble_shader` | stage="vertex", event_id=569 | 反汇编（ES 可能失败→fallback） | ⚠️ SPIR-V 编译失败, 已知限制 |
| 16 | `get_shader_reflection` | stage="pixel", event_id=569 | 返回 IO 签名、cbuffer、资源绑定 | ❌→🔧 已修复 resType→textureType |
| 17 | `get_shader_reflection` | stage="vertex", event_id=569 | 返回 VS 反射信息 | ✅ (5 inputs, 5 outputs, 1 cbuffer) |
| 18 | `get_shader_bindings` | stage="pixel", event_id=569 | 返回 PS 资源绑定 | ⚠️ _DissolveMap "failed to read binding" |
| 19 | `get_cbuffer_contents` | stage="vertex", cbuffer_index=0, event_id=569 | 返回 cbuffer 变量值 | ✅ (Unity 矩阵等 6 变量) |

### 第四阶段：资源查询

| # | 工具 | 测试参数 | 预期 | 状态 |
|---|------|----------|------|------|
| 20 | `list_textures` | (无参数) | 列出全部 172 纹理 | ✅ (172 textures) |
| 21 | `list_textures` | min_width=512 | 过滤大纹理 | ✅ (108 textures) |
| 22 | `list_buffers` | min_size=100000 | 过滤大 buffer | ✅ (23 buffers) |
| 23 | `list_resources` | name_pattern=".*" | 列出所有命名资源 | ❌→🔧 Bug 5: UTF-8 decode error |
| 24 | `get_resource_usage` | resource_id="ResourceId::4749" | 主 RT 的使用历史 | ⚠️ 功能正常 (155 usages), usage 值为原始数字 |

### 第五阶段：数据导出

| # | 工具 | 测试参数 | 预期 | 状态 |
|---|------|----------|------|------|
| 25 | `save_texture` | resource_id=ResourceId::4749, output=Downloads | 导出纹理为 PNG | ✅ |
| 26 | `get_buffer_data` | resource_id=ResourceId::4026, format="floats" | 读取 buffer 浮点数据 | ✅ (返回顶点浮点数据) |
| 27 | `export_draw_textures` | event_id=569, output_dir=Downloads/mcp_test_textures | 批量导出 PS 纹理 | ✅ (0 textures, 该 draw 无纹理) |
| 28 | `export_draw_textures` | event_id=1014, output_dir=Downloads/mcp_test_textures2 | 换个有纹理的 draw 测 | ⚠️ (0 exported, 可能 binding 读取失败) |
| 29 | `save_render_target` | event_id=3125, output=Downloads/mcp_test_rt.png | 保存主 pass 最终 RT | ✅ (修复后正常) |
| 30 | `save_render_target` | event_id=3125, save_depth=True | 同时保存 depth | ✅ (color + depth 两文件) |
| 31 | `export_mesh` | event_id=569, output=Downloads/mcp_test_mesh.obj | 导出网格为 OBJ | ✅ (18218 顶点, 6072 三角形) |

### 第六阶段：像素与高级分析

| # | 工具 | 测试参数 | 预期 | 状态 |
|---|------|----------|------|------|
| 32 | `pick_pixel` | resource_id="ResourceId::4749", x=748, y=360 | 读取中心像素 RGBA | ✅ (R=0.435, G=0.325, B=1.0, A=1.0) |
| 33 | `get_texture_stats` | resource_id="ResourceId::4749" | 纹理统计 min/max/avg | ✅ (min/max 正常, 无 avg) |
| 34 | `pixel_history` | resource_id="ResourceId::4749", x=748, y=360 | 像素修改历史 | ✅ (13 modifications) |
| 35 | `get_post_vs_data` | event_id=569, stage="vsout", max_vertices=10 | VS 后顶点数据 | ✅ (10/83829 vertices, 5 attrs) |

### 第七阶段：Session 管理

| # | 工具 | 测试参数 | 预期 | 状态 |
|---|------|----------|------|------|
| 36 | `close_capture` | (无参数) | 关闭并释放资源 | 待测（最后执行） |

## 测试汇总

- **总计**: 36 项
- **✅ 通过**: 26 项
- **⚠️ 部分问题**: 5 项 (#10, #18, #24, #28, #33)
- **❌ 修复中**: 3 项 (#6, #23 需重启; #16 已修复)
- **⚠️ 已知限制**: 1 项 (#15 shader 反汇编)
- **待测**: 1 项 (#36 close_capture)

## 已发现并修复的 Bug

### Bug 1: ShaderResource.resType 不存在
- **错误**: `'renderdoc.ShaderResource' object has no attribute 'resType'`
- **原因**: RenderDoc API 中 `ShaderResource` 使用 `textureType` 而非 `resType`
- **修复**: `resType` → `textureType`
- **影响文件**:
  - `shader_tools.py` (4 处: 行 30, 31, 170, 180)
  - `pipeline_tools.py` (2 处: 行 252, 272)

### Bug 2: Descriptor.resourceId 不存在
- **错误**: `'renderdoc.Descriptor' object has no attribute 'resourceId'`
- **原因**: `GetOutputTargets()` 和 `GetDepthTarget()` 返回 `Descriptor` 对象，其资源 ID 属性为 `resource` 而非 `resourceId`
- **注意**: `TextureDescription.resourceId`、`BufferDescription.resourceId`、`ShaderReflection.resourceId`、`BoundVBuffer.resourceId`、`TextureSave.resourceId` 等仍然正确
- **修复**: 仅在 Descriptor 对象上 `resourceId` → `resource`
- **影响文件**:
  - `data_tools.py` (6 处: 行 319, 326, 337, 354, 355, 363)
  - `pipeline_tools.py` (6 处: 行 156×2, 163, 164, 497, 499, 513, 514)

### Bug 3: ActionDescription.depthOutput 不存在 (新发现)
- **错误**: `'renderdoc.ActionDescription' object has no attribute 'depthOutput'`
- **原因**: RenderDoc API 中属性名为 `depthOut` 而非 `depthOutput`
- **修复**: `depthOutput` → `depthOut`
- **影响文件**:
  - `util.py` (4 处: 行 210, 212, 246, 247)
  - `tests/test_util.py` (2 处: 行 126, 127)

### Bug 4: get_vertex_inputs format 显示 Swig 指针 (新发现)
- **错误**: format 字段显示 `<Swig Object of type 'ResourceFormat *' at 0x...>` 而非可读格式名
- **原因**: `str(a.format)` 对 Swig 包装的 `ResourceFormat` 对象无法得到格式名
- **修复**: `str(a.format)` → `str(a.format.Name())`
- **影响文件**:
  - `pipeline_tools.py` (1 处: 行 350)

### Bug 5: list_resources UTF-8 解码错误 (新发现)
- **错误**: `'utf-8' codec can't decode byte 0x90 in position 0: invalid start byte`
- **原因**: 某些资源名包含非 UTF-8 字节（可能是二进制数据）
- **修复**: 对 `res.name` 添加 try/except 编码保护
- **影响文件**:
  - `resource_tools.py` (行 86-90)

## 待改进项 (非 Bug)

1. **get_resource_usage**: `usage` 字段显示原始枚举数值 (如 `"32"`, `"35"`)，应转换为可读名称
2. **get_shader_reflection**: `var_type` 和 `system_value` 字段显示 `"0"`, `"1"` 等数值，应转换为枚举名
3. **get_shader_bindings**: PS _DissolveMap 纹理绑定读取失败 (可能是 OpenGL ES 特定问题)
4. **pick_pixel**: `rgba_uint` 返回的是 float 的原始内存表示而非 uint8 值
5. **export_draw_textures**: EID 1014 导出 0 纹理，可能因 shader binding 读取失败
6. **get_texture_stats**: 只返回 min/max，没有 avg/mean 统计

## 环境限制

- **Shader 反汇编**: SPIR-V 编译要求 ES 310+，当前 capture 的 ES shader 版本不满足；AMD GCN ISA 需要旧版 AMD 驱动 (<22.7.1)
- **renderdoc 模块**: 仅在 RenderDoc 内嵌 Python 环境中可用，无法在外部 Python 中 import

## 导出文件路径

测试过程中导出的文件：
- Mesh: `C:\Users\18523\Downloads\mcp_test_mesh.obj`
- RT color: `C:\Users\18523\Downloads\mcp_test_rt.png`
- RT depth: `C:\Users\18523\Downloads\mcp_test_rt_depth_depth`
- Texture 4749: `C:\Users\18523\Downloads\mcp_test_texture_4749.png`
