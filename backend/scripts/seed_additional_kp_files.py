from __future__ import annotations

import json
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
CURRICULA_DIR = BACKEND_DIR / "data" / "curricula"
KP_DIR = BACKEND_DIR / "static" / "kp"


def build_graph(topics: list[str]) -> dict:
    categories = [
        {"name": "基础概念"},
        {"name": "核心方法"},
        {"name": "应用实践"},
    ]
    total = max(len(topics), 1)
    nodes = [
        {"id": topic, "category": min(index * len(categories) // total, len(categories) - 1)}
        for index, topic in enumerate(topics)
    ]
    links = [
        {"source": topics[index], "target": topics[index + 1]}
        for index in range(len(topics) - 1)
    ]
    if len(topics) >= 5:
        links.extend([
            {"source": topics[0], "target": topics[3]},
            {"source": topics[1], "target": topics[-1]},
        ])
    return {"nodes": nodes, "links": links, "categories": categories}


KP_TOPICS: dict[str, list[str]] = {
    "新生研讨课.json": ["专业认知", "培养方案理解", "大学学习方法", "信息检索与学术规范", "工程伦理", "学习规划"],
    "计算科学导论.json": ["计算模型", "算法思维", "数据抽象", "系统思维", "计算复杂性", "软件工程基础", "人工智能概览"],
    "人工智能导论.json": ["人工智能基本概念", "搜索与问题求解", "知识表示与推理", "机器学习基础", "深度学习概念", "自然语言处理概览", "计算机视觉概览", "AI伦理与安全"],
    "大学物理.json": ["质点运动学", "牛顿运动定律", "功与能", "动量与角动量", "刚体力学", "振动与波动", "静电场", "稳恒磁场", "电磁感应", "光学基础"],
    "数据分析Python.json": ["Python数据处理基础", "NumPy数组计算", "Pandas数据清洗", "数据可视化", "描述统计分析", "探索性数据分析", "特征工程基础", "分析报告表达"],
    "最优化方法.json": ["优化模型", "凸集与凸函数", "一阶最优性条件", "梯度下降法", "牛顿法", "约束优化", "拉格朗日乘子", "KKT条件", "线性规划基础"],
    "计算机组成原理.json": ["数据表示", "指令系统", "运算器", "控制器", "CPU流水线", "存储层次结构", "Cache机制", "输入输出系统", "总线结构"],
    "石油与人工智能.json": ["油气业务场景", "工业数据治理", "智能勘探", "智能钻井", "生产优化", "设备预测维护", "智能油田应用", "工业AI安全"],
    "数字图像处理.json": ["图像采样与量化", "灰度变换", "直方图均衡", "空间滤波", "频域滤波", "图像复原", "边缘检测", "图像分割", "形态学处理"],
    "计算智能.json": ["进化计算", "遗传算法", "粒子群优化", "蚁群算法", "模糊逻辑", "神经计算", "群智能优化"],
    "可视化导论.json": ["数据类型与视觉通道", "图表选择", "可视化编码", "交互可视化", "多维数据可视化", "网络图可视化", "可视分析流程"],
    "矩阵理论与计算.json": ["矩阵分解", "特征值与特征向量", "奇异值分解", "正定矩阵", "矩阵范数", "稀疏矩阵计算", "迭代法"],
    "机器学习实践.json": ["数据集划分", "特征工程实践", "模型训练流程", "超参数调优", "模型评估报告", "模型部署基础", "实验复现"],
    "前沿信息技术.json": ["云计算", "边缘计算", "物联网", "区块链", "大模型应用", "隐私计算", "信息安全前沿"],
    "大模型技术及应用.json": ["Transformer结构", "预训练与微调", "提示工程", "RAG检索增强", "Agent工具调用", "模型评估", "安全与对齐", "应用开发流程"],
    "计算机图形学.json": ["图形渲染管线", "几何变换", "投影与裁剪", "光照模型", "纹理映射", "曲线曲面", "光栅化", "三维建模"],
    "大数据技术与应用.json": ["分布式文件系统", "MapReduce模型", "Spark计算模型", "数据仓库", "流式计算", "数据湖", "大数据治理", "大数据应用案例"],
    "具身智能技术.json": ["感知决策控制闭环", "机器人运动学", "环境感知", "路径规划", "强化学习控制", "多模态交互", "仿真训练"],
    "无人驾驶技术.json": ["自动驾驶架构", "传感器融合", "车道线检测", "目标检测与跟踪", "定位与建图", "路径规划", "运动控制", "安全验证"],
    "油气勘探开发技术.json": ["油气地质基础", "地震勘探", "测井解释", "储层建模", "钻井工程", "采油工程", "油藏数值模拟", "智能油田"],
    "人工智能综合实习.json": ["需求分析", "数据准备", "模型选择", "训练与评估", "系统集成", "实验报告", "项目展示"],
    "计算方法.json": ["误差分析", "非线性方程求解", "线性方程组数值解", "插值方法", "数值积分", "数值微分", "常微分方程数值解"],
    "知识图谱技术及应用.json": ["实体关系抽取", "本体建模", "知识融合", "图数据库", "图查询语言", "知识推理", "知识图谱问答", "行业应用"],
    "群智感知与社会计算.json": ["群智感知模型", "众包任务分配", "数据质量控制", "社交网络分析", "信息传播模型", "隐私保护", "城市计算应用"],
    "信号分析与处理.json": ["连续与离散信号", "傅里叶变换", "采样定理", "卷积与相关", "数字滤波器", "频谱分析", "小波变换"],
    "时间序列分析.json": ["平稳性", "自相关与偏自相关", "ARMA模型", "ARIMA模型", "季节性模型", "预测评估", "异常检测", "深度时间序列"],
    "毕业设计.json": ["选题与需求分析", "文献综述", "技术方案设计", "系统实现", "实验评估", "论文写作", "答辩展示"],
    "计算机系统导论.json": ["计算机抽象层次", "程序执行过程", "数据表示", "机器级程序", "存储系统", "操作系统接口", "网络与并发基础"],
    "数字逻辑与EDA技术.json": ["数制与编码", "布尔代数", "组合逻辑电路", "时序逻辑电路", "触发器与寄存器", "有限状态机", "Verilog基础", "EDA仿真"],
    "编译原理.json": ["词法分析", "正则表达式与自动机", "语法分析", "语法制导翻译", "中间代码生成", "运行时存储管理", "代码优化", "目标代码生成"],
    "信息安全.json": ["安全威胁模型", "密码学基础", "身份认证", "访问控制", "网络安全", "系统安全", "应用安全", "安全审计"],
    "物联网与边缘计算.json": ["物联网体系结构", "传感器数据采集", "通信协议", "边缘计算架构", "边云协同", "设备管理", "物联网安全"],
    "云计算技术与应用.json": ["虚拟化技术", "容器技术", "云服务模型", "分布式存储", "弹性伸缩", "云原生应用", "云安全"],
    "计算机体系结构.json": ["指令级并行", "流水线优化", "Cache一致性", "多核处理器", "存储层次优化", "并行体系结构", "性能评估"],
    "区块链技术与应用.json": ["哈希与签名", "区块结构", "共识机制", "智能合约", "联盟链", "链上数据治理", "区块链应用"],
    "软件分析与设计.json": ["需求建模", "用例分析", "领域模型", "架构设计", "设计模式", "接口设计", "UML建模", "设计评审"],
    "人机交互.json": ["用户研究", "交互设计原则", "原型设计", "可用性测试", "信息架构", "视觉一致性", "无障碍设计"],
    "工业互联网导论.json": ["工业互联网体系", "工业协议", "工业数据采集", "边缘网关", "工业平台", "设备联网", "工业安全"],
    "形式化方法.json": ["形式化规格说明", "命题逻辑", "时序逻辑", "模型检测", "定理证明", "程序验证", "不变式"],
    "软件测试与质量保证.json": ["测试用例设计", "单元测试", "集成测试", "系统测试", "自动化测试", "缺陷管理", "质量度量"],
    "石油工业软件基础.json": ["石油业务流程", "工业软件架构", "专业数据模型", "数值模拟基础", "软件集成", "行业标准", "工程应用"],
    "软件安全.json": ["安全需求", "威胁建模", "安全编码", "漏洞检测", "身份与权限", "安全测试", "安全运维"],
    "软件可靠性分析.json": ["可靠性指标", "故障模型", "可靠性预测", "容错设计", "可靠性测试", "运行数据分析", "可靠性增长模型"],
    "软件分析与验证.json": ["静态分析", "动态分析", "符号执行", "模型检查", "程序切片", "缺陷定位", "验证报告"],
    "工业App开发.json": ["工业场景需求", "移动端架构", "设备数据接口", "可视化看板", "离线同步", "权限管理", "发布运维"],
    "软件体系结构.json": ["架构风格", "分层架构", "微服务架构", "架构视图", "质量属性", "架构评估", "架构演化"],
    "软件工程管理与项目实践.json": ["项目计划", "需求管理", "进度管理", "风险管理", "团队协作", "持续集成", "项目复盘"],
    "领域软件开发.json": ["领域分析", "领域模型", "领域专用语言", "业务规则建模", "领域服务", "领域驱动设计", "行业适配"],
    "模型驱动开发.json": ["元模型", "模型转换", "代码生成", "模型验证", "低代码平台", "模型演化", "工具链集成"],
    "架构驱动开发.json": ["架构需求", "架构决策", "组件划分", "接口契约", "架构约束", "架构实现映射", "架构治理"],
    "可信软件技术应用.json": ["可信需求", "可信度量", "形式化验证", "安全可靠设计", "故障注入", "可信评估", "可信运维"],
    "油气大数据处理.json": ["油气数据采集", "数据清洗", "地震数据处理", "测井数据分析", "生产数据分析", "大数据平台", "智能决策"],
    "工业软件平台设计.json": ["平台架构", "插件机制", "数据总线", "工作流引擎", "可视化建模", "权限体系", "平台运维"],
    "智能软件应用.json": ["智能需求识别", "模型服务集成", "知识检索", "智能推荐", "人机协同", "效果评估", "应用迭代"],
    "工业大数据处理.json": ["工业数据源", "实时数据采集", "异常检测", "预测维护", "质量分析", "工业知识建模", "数据安全"],
    "GeoEast-iEco开发.json": ["GeoEast平台基础", "iEco开发流程", "地震数据管理", "插件开发", "解释流程集成", "性能优化", "行业应用"],
    "专业实训.json": ["项目选题", "需求分析", "方案设计", "编码实现", "测试验证", "团队协作", "成果汇报"],
    "数字孪生与虚拟交互.json": ["数字孪生模型", "三维场景构建", "实时数据驱动", "虚拟交互", "仿真验证", "可视化监控", "应用集成"],
    "高性能计算.json": ["并行计算模型", "多线程编程", "GPU计算", "MPI并行", "性能剖析", "负载均衡", "集群作业调度"],
    "人类行为识别.json": ["行为数据采集", "人体姿态估计", "时序特征提取", "行为分类模型", "多模态融合", "异常行为检测", "应用评估"],
}


COURSE_KP_FILE_BY_ID = {
    "freshman_seminar": "新生研讨课.json",
    "cs_intro": "计算科学导论.json",
    "computing_intro": "计算科学导论.json",
    "ai_intro": "人工智能导论.json",
    "college_physics": "大学物理.json",
    "college_physics_lab": "大学物理.json",
    "data_analysis_python": "数据分析Python.json",
    "programming_practice": "程序设计基础.json",
    "optimization_method": "最优化方法.json",
    "computer_composition": "计算机组成原理.json",
    "oil_ai": "石油与人工智能.json",
    "digital_image_processing": "数字图像处理.json",
    "computational_intelligence": "计算智能.json",
    "visualization_intro": "可视化导论.json",
    "matrix_theory_computation": "矩阵理论与计算.json",
    "machine_learning_practice": "机器学习实践.json",
    "frontier_it": "前沿信息技术.json",
    "llm_application": "大模型技术及应用.json",
    "computer_graphics": "计算机图形学.json",
    "big_data": "大数据技术与应用.json",
    "embodied_ai": "具身智能技术.json",
    "autonomous_driving": "无人驾驶技术.json",
    "oil_gas_technology": "油气勘探开发技术.json",
    "ai_comprehensive_practice": "人工智能综合实习.json",
    "calculation_method": "计算方法.json",
    "knowledge_graph": "知识图谱技术及应用.json",
    "crowd_sensing_social_computing": "群智感知与社会计算.json",
    "signal_processing": "信号分析与处理.json",
    "time_series_analysis": "时间序列分析.json",
    "graduation_design": "毕业设计.json",
    "computer_system_intro": "计算机系统导论.json",
    "digital_logic_eda": "数字逻辑与EDA技术.json",
    "database_course_design": "数据库系统.json",
    "compiler_principle": "编译原理.json",
    "network_course_design": "计算机网络.json",
    "system_capability_practice": "计算机系统导论.json",
    "os_course_design": "操作系统.json",
    "compiler_course_design": "编译原理.json",
    "information_security": "信息安全.json",
    "iot_edge": "物联网与边缘计算.json",
    "cloud_computing": "云计算技术与应用.json",
    "computer_architecture": "计算机体系结构.json",
    "blockchain": "区块链技术与应用.json",
    "software_analysis_design": "软件分析与设计.json",
    "human_computer_interaction": "人机交互.json",
    "industrial_internet_intro": "工业互联网导论.json",
    "formal_methods": "形式化方法.json",
    "software_testing_quality": "软件测试与质量保证.json",
    "petroleum_software_foundation": "石油工业软件基础.json",
    "software_security": "软件安全.json",
    "software_reliability": "软件可靠性分析.json",
    "software_analysis_verification": "软件分析与验证.json",
    "industrial_app_development": "工业App开发.json",
    "software_architecture": "软件体系结构.json",
    "software_project_management": "软件工程管理与项目实践.json",
    "domain_software_development": "领域软件开发.json",
    "model_driven_development": "模型驱动开发.json",
    "architecture_based_development": "架构驱动开发.json",
    "reliability_software_application": "可信软件技术应用.json",
    "oil_gas_big_data": "油气大数据处理.json",
    "industrial_platform_design": "工业软件平台设计.json",
    "intelligent_software_application": "智能软件应用.json",
    "industrial_big_data": "工业大数据处理.json",
    "geoeast_ieco_development": "GeoEast-iEco开发.json",
    "digital_twin_virtual_interaction": "数字孪生与虚拟交互.json",
    "high_performance_computing": "高性能计算.json",
    "human_behavior_recognition": "人类行为识别.json",
    "basic_training_1": "专业实训.json",
    "basic_training_2": "专业实训.json",
    "engineering_training_1": "专业实训.json",
    "engineering_training_2": "专业实训.json",
    "engineering_training_3": "专业实训.json",
    "engineering_training_4": "专业实训.json",
    "enterprise_training": "专业实训.json",
    "job_internship": "专业实训.json",
    "professional_integrated_practice": "专业实训.json",
}


def seed_kp_graphs() -> int:
    KP_DIR.mkdir(parents=True, exist_ok=True)
    count = 0
    for filename, topics in KP_TOPICS.items():
        target = KP_DIR / filename
        target.write_text(
            json.dumps(build_graph(topics), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        count += 1
    return count


def update_curricula() -> tuple[int, list[str]]:
    updated = 0
    unresolved: set[str] = set()
    for path in sorted(CURRICULA_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        changed = False
        for course in data.get("courses", []):
            if course.get("kp_file"):
                continue
            course_id = course.get("id")
            kp_file = COURSE_KP_FILE_BY_ID.get(course_id)
            if not kp_file:
                unresolved.add(str(course_id))
                continue
            course["kp_file"] = kp_file
            updated += 1
            changed = True
        if changed:
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return updated, sorted(unresolved)


if __name__ == "__main__":
    graph_count = seed_kp_graphs()
    update_count, unresolved_ids = update_curricula()
    print(f"seeded kp files: {graph_count}")
    print(f"updated curriculum courses: {update_count}")
    if unresolved_ids:
        print("unresolved course ids:")
        for course_id in unresolved_ids:
            print(f"- {course_id}")
