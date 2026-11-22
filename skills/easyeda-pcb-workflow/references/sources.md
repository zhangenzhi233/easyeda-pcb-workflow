# 方法出处与复看位置

两个上游项目分别提供 API 对象模型和带回读的操作方法；本技能将其用于绘图和验收。以下链接固定到此次核对的源码版本。[官方 easyeda-api，中文入口](https://github.com/easyeda/easyeda-api-skill/blob/998c0e304afaa813540b7446489982bc5256d37e/README.zh-Hans.md) · [easyeda-agent，实际技能入口](https://github.com/zhoushoujianwork/easyeda-agent/blob/df81b7006ccd7b56c0178f69abff38738b74e69b/.agents/skills/easyeda-agent/SKILL.md)

四个系列覆盖基础版 29 集、大师篇 20 集、梁山派四层 37 集、逻辑派六层 60 集。下面按画板时要解决的问题列复看入口，时间为分集内时间。

| 现场问题 | 可迁移的操作 | 对照原片 |
|---|---|---|
| 双运放符号好读，怎样保证实体方向正确？ | 按手册填针号，独立核封装尺度、脚距与 1 脚，再将符号与焊盘逐针对应。 | [基础 P16 03:13](https://www.bilibili.com/video/BV1At421h7Ui/?p=16&t=193) · [P17 09:55](https://www.bilibili.com/video/BV1At421h7Ui/?p=17&t=595) |
| 放好端口后，插头真的插得进吗？ | 板边先给连接器和插拔包络留空间，试走一束关键线，受阻时回调布局。 | [基础 P27 09:00](https://www.bilibili.com/video/BV1At421h7Ui/?p=27&t=540) · [P28 04:08](https://www.bilibili.com/video/BV1At421h7Ui/?p=28&t=248) |
| 原理图跨区过长，元件值看不清怎么办？ | 重新安排图幅和模块，把默认状态、选装条件和有电气属性的短网标放到相应端点。 | [大师 P8 08:05](https://www.bilibili.com/video/BV1fFAfeZEBE/?p=8&t=485) · [P10 19:17](https://www.bilibili.com/video/BV1fFAfeZEBE/?p=10&t=1157) |
| 相近的电容、连接器怎样摆出依据？ | 先按电路块交叉选件，整板再量接口间隙。若供电线绕过电容而形成长支路，回到布局调整。 | [大师 P11 14:25](https://www.bilibili.com/video/BV1fFAfeZEBE/?p=11&t=865) · [P12 31:39](https://www.bilibili.com/video/BV1fFAfeZEBE/?p=12&t=1899) · [P15 24:10](https://www.bilibili.com/video/BV1fFAfeZEBE/?p=15&t=1450) |
| 铺铜、针表和间距怎样验收？ | 重铺后定位遗留地飞线，根据真实排针排丝印，点击间距报告定位到具体过孔。 | [大师 P16 18:13](https://www.bilibili.com/video/BV1fFAfeZEBE/?p=16&t=1093) · [P17 03:30](https://www.bilibili.com/video/BV1fFAfeZEBE/?p=17&t=210) · [基础 P24 23:28](https://www.bilibili.com/video/BV1At421h7Ui/?p=24&t=1408) |
| SDRAM 有分支，该比较哪一段？ | 给网络类赋规则，将芯片到芯片、到外接座子的路径分别设为焊盘组，再按组核对长度。 | [四层 P16 01:52](https://www.bilibili.com/video/BV1sbTTzwEmj/?p=16&t=112) · [P27 06:14](https://www.bilibili.com/video/BV1sbTTzwEmj/?p=27&t=374) |
| DRC 通过后还能从哪里找问题？ | 把实际光绘和钻孔送入独立 DFM 查看器，检查孔环和阻焊。改板后重新导出。 | [四层 P36 07:54](https://www.bilibili.com/video/BV1sbTTzwEmj/?p=36&t=474) · [P37 10:16](https://www.bilibili.com/video/BV1sbTTzwEmj/?p=37&t=616) |
| BGA 要几层，为什么不同层线宽不同？ | 根据扇出与布线通道选叠层，在板厂模型里指定信号层和参考层，再把计算值分配给对应网络类。 | [六层 P15 03:32](https://www.bilibili.com/video/BV1MTP1e6Euo/?p=15&t=212) · [P17 08:24](https://www.bilibili.com/video/BV1MTP1e6Euo/?p=17&t=504) |
| DDR3 与 HDMI 怎样分组？ | 区分字节内的 DQ/DM/DQS、时钟与地址组、差分对内偏斜；换层后追实际参考面和回流孔。 | [六层 P26 02:32](https://www.bilibili.com/video/BV1MTP1e6Euo/?p=26&t=152) · [P48 05:07](https://www.bilibili.com/video/BV1MTP1e6Euo/?p=48&t=307) · [P57 40:27](https://www.bilibili.com/video/BV1MTP1e6Euo/?p=57&t=2427) |

实例复核可以用作者的原生工程、成品 Gerber 及飞针表交叉验证。课程示例的线宽、介质、孔径、针排间距或芯片规则，迁移时应当根据新板的器件与板厂规格重新确定。[大师篇作者的原生工程](https://github.com/physicsexpert/Master-chapter-EasyEDA-Professional-Edition-course-open-source-materials/tree/87f2af3462463ad44c9216ba6538cccf250b5ece)
