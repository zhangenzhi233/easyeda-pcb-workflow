# 选对通道，复开后读回

先看用户打开的宿主。下表是两种工具的用法，同一设计的写入由一条通道顺序完成。命令和返回字段以本机版本的帮助为准。

| 工具 | 适合做什么 | 第一个可观察结果 |
|---|---|---|
| 官方 `easyeda-api` | 查真实 `eda.*` 类、方法签名、单位、支持版本和文档格式。在已连接网关或支持官方 CLI 的专业版桌面会话中执行。 | `eda.dmt_Project.getCurrentProjectInfo()` 返回目标工程，`eda.dmt_SelectControl.getCurrentDocumentInfo()` 返回目标文档 UUID 和类型。使用官方桥接时同时核对客户端连接与目标身份。 |
| `easyeda-agent` | 指定使用它的 V4 Web 编辑器/连接器时，按阶段取说明、做预检，用 typed 命令改动，再查实际连接与几何。其离线目录也可用来查方法和数据格式。 | `easyeda --version`、`easyeda health` 后查看目标，`easyeda doc ls` 与 `easyeda doc ready` 核对当前页。离线查到指令只表示有此接口。 |

### 在桌面专业版中

1. 若已开放原生命令行，先用 `lceda-pro doc api --class-name PCB_Document` 等按类查方法。用已知会话 ID 操作，或从项目副本新开指定会话。点开原理图或 PCB 后，等文档就绪并读回 UUID；避免对另一个同名标签执行。只有走官方 Bridge 路线时才需要其本地服务和网关扩展。
2. 旧工程正在编辑时，先从当前会话导出快照，与磁盘版本逐对象比对。保留用户手动移过的位号、走线和器件，基于包含这些变更的副本修改。文档同名时记录会话、路径和文档 UUID。批量创建前用一个已知封装核对原点、角度、单位与一脚，底面再用一个非对称文字实导确认镜像。原理图导入 PCB 时核对新增、删除、移动清单及当前规则。
3. 分别在原理图页、PCB 页运行原生检查。可在当前 API 帮助中查 `sch_Drc.check`、`pcb_Drc.checkDetailed`、`pcb_PrimitivePour.getAll` 和 `rebuildCopperRegion`。检查实际覆盖的页面、规则配置、未布通和铜区。保存要读取操作回执，交付要从磁盘复开工程并再次读取。
4. 在原理图与 PCB 各自激活时用 `sch_ManufactureData.getNetlistFile`、`pcb_ManufactureData.getNetlistFile` 分别导出原生 ENET，另存不同文件名。专业版版本差异可能使按文档 UUID 的比较器读到空 PCB 侧；这时采用两份实际导出文件逐针查证，再核对实际铜层，将异常入口及替代结果记录在案。

### 在 easyeda-agent 中

- 通过 `easyeda skill read --stage schematic`、`--stage pcb-layout`、`--stage pcb-routing` 或 `--stage check` 取所需章节；用 `easyeda actions`、具体子命令的 `--help` 确认参数与返回值。记录版本，离线章节需要其自带资源或有效的 `--skill-root`。
- 选择准确的 `--project` 和 `--doc`，基于刚读的对象 ID 或快照形成变更。有 dry-run 的操作先看对象和数量，按既有授权推进约定阶段；通过 typed 命令或 `easyeda apply` 写入。当前上游的交互式整板布局流程设有布局展示与确认环节；使用该模式时在用户选定的审阅点展示实际读回的布局。
- 核对写入的数量、元件实际位置和电气网络。遇到部分写入或超时，先检查对话框、当前文档和已存在的对象，只对缺失项重新制定操作。保存步骤读取明确的 `saved: true`，再按版本支持的 `doc reload` 和新回读核对；`ok` 表示调用层的状态。
- 目标宿主当前不可写时，可继续审已导出的工程、网表和制造文件，并说明现场编辑尚待验证。已有本机桌面通道时可根据用户指定的宿主选用官方路线，无须只为查文档另装扩展。

上游版本和教程入口见[来源](sources.md)。
