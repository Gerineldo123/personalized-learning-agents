import json
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from api.deps import get_db
from core.database import SessionLocal
from core.llm_client import chat_completion
from models.student import StudentProfile
from models.quiz_record import QuizRecord
from models.conversation import Conversation, ChatMessage
from schemas.student import ProfileCreate, ProfileResponse, QuestionnaireRequest
from agents.base import AgentState
from agents.profile_agent import ProfileAgent

router = APIRouter(prefix="/api/profile", tags=["画像"])

EDUCATION_LEVELS = ["专科生", "本科生", "硕士研究生", "博士研究生"]
YEARS_BY_LEVEL = {
    "专科生": ["大一", "大二", "大三"],
    "本科生": ["大一", "大二", "大三", "大四", "大五"],
    "硕士研究生": ["研一", "研二", "研三"],
    "博士研究生": ["博一", "博二及以上"],
}
DISCIPLINES = [
    "哲学", "经济学", "法学", "教育学", "文学", "历史学",
    "理学", "工学", "农学", "医学", "军事学", "管理学", "艺术学", "交叉学科",
]
COURSE_GOALS = [
    "短期应试", "长期应试", "项目驱动", "扎实基础",
]
DIFFICULTY_TYPES = [
    "概念理解不透彻", "公式/理论记不住", "解题没思路",
    "代码编写或实验操作困难", "知识太多太杂，抓不住重点",
]
IMPACTS = [
    "担心挂科或补考", "后续课程听不懂",
    "考研/保研复习受阻", "单纯想学懂，没有具体考试压力",
]


@router.get("")
def get_profile(user_id: str, db: Session = Depends(get_db)):
    from models.profile_history import ProfileHistory
    profile = db.query(StudentProfile).filter(
        StudentProfile.user_id == user_id
    ).first()
    if not profile:
        return {"found": False, "user_id": user_id}

    p = ProfileResponse.model_validate(profile).model_dump()

    # 画像健全度
    checks = [
        p.get("major"), p.get("grade") or p.get("education_level"),
        p.get("learning_goal"), p.get("cognitive_style"),
        bool(p.get("weak_points")), bool(p.get("preferred_format")),
        bool(p.get("weak_courses")),
        bool(p.get("ability_scores") and any(v for v in p["ability_scores"].values())),
    ]
    completeness = round(sum(1 for c in checks if c) / len(checks) * 100)

    # 历史快照（最近30条）
    history = db.query(ProfileHistory).filter(
        ProfileHistory.user_id == user_id
    ).order_by(ProfileHistory.created_at.asc()).limit(30).all()
    history_list = [
        {
            "trigger": h.trigger,
            "snapshot": h.snapshot,
            "created_at": h.created_at.isoformat() if h.created_at else None,
        }
        for h in history
    ]

    return {"found": True, "profile": p, "completeness": completeness, "history": history_list}


@router.delete("")
def delete_profile(user_id: str, db: Session = Depends(get_db)):
    profile = db.query(StudentProfile).filter(
        StudentProfile.user_id == user_id
    ).first()
    if not profile:
        return {"ok": True, "deleted": False, "message": "画像不存在"}
    db.delete(profile)
    db.commit()
    return {"ok": True, "deleted": True, "message": "画像已删除"}


def questionnaire_config():
    return {
        "education_levels": EDUCATION_LEVELS,
        "years_by_level": YEARS_BY_LEVEL,
        "disciplines": DISCIPLINES,
        "course_goals": COURSE_GOALS,
        "difficulty_types": DIFFICULTY_TYPES,
        "impacts": IMPACTS,
    }


def seed_courses(discipline: str = "", level: str = "", major: str = ""):
    MAJOR_SEEDS: dict[str, list[str]] = {
        # === 工学 ===
        "计算机科学与技术":    ["程序设计基础", "数据结构", "计算机组成原理", "操作系统", "计算机网络", "编译原理", "数据库系统", "软件工程"],
        "软件工程":            ["面向对象程序设计", "数据结构", "软件工程概论", "数据库系统", "操作系统", "计算机网络", "软件测试", "软件项目管理"],
        "网络工程":            ["计算机网络", "数据结构", "操作系统", "网络协议分析", "网络安全", "路由与交换技术", "数据库系统", "网络工程规划"],
        "信息安全":            ["密码学", "网络安全", "操作系统", "数据结构", "数据库系统", "计算机组成原理", "逆向工程", "漏洞挖掘"],
        "物联网工程":          ["物联网导论", "传感器原理", "嵌入式系统", "无线传感网络", "RFID原理", "数据库系统", "计算机网络", "操作系统"],
        "数据科学与大数据技术":["Python程序设计", "数据结构", "数据库系统", "概率论与数理统计", "机器学习", "大数据技术", "数据可视化", "分布式计算"],
        "智能科学与技术":      ["人工智能导论", "机器学习", "深度学习", "自然语言处理", "计算机视觉", "数据结构", "模式识别", "知识图谱"],
        "人工智能":            ["人工智能导论", "机器学习", "深度学习", "计算机视觉", "自然语言处理", "强化学习", "数据结构", "认知科学"],
        "数字媒体技术":        ["计算机图形学", "数字图像处理", "游戏引擎", "三维建模", "数据结构", "人机交互", "动画设计", "虚拟现实"],
        "网络空间安全":        ["密码学", "网络安全", "系统安全", "软件安全", "数据结构", "操作系统", "信息内容安全", "网络攻防"],
        "电子信息工程":        ["电路分析", "模拟电子技术", "数字电子技术", "信号与系统", "通信原理", "电磁场", "微机原理", "数字信号处理"],
        "电子科学与技术":      ["固体物理", "半导体物理", "微电子器件", "集成电路设计", "电路分析", "信号与系统", "模拟电子技术", "数字电子技术"],
        "通信工程":            ["通信原理", "信号与系统", "数字信号处理", "电磁场", "移动通信", "光纤通信", "计算机网络", "信息论"],
        "微电子科学与工程":    ["半导体物理", "集成电路设计", "模拟集成电路", "数字集成电路", "半导体工艺", "固体物理", "微电子封装", "EDA技术"],
        "集成电路设计与集成系统": ["数字集成电路设计", "模拟集成电路设计", "EDA技术", "半导体物理", "集成电路工艺", "SoC设计", "嵌入式系统", "VLSI设计"],
        "自动化":              ["自动控制原理", "现代控制理论", "传感器与检测技术", "电机与拖动", "电力电子技术", "微机原理", "过程控制", "运动控制"],
        "机器人工程":          ["机器人学", "自动控制原理", "传感器技术", "电机驱动", "计算机视觉", "嵌入式系统", "运动学", "SLAM技术"],
        "机械工程":            ["理论力学", "材料力学", "机械设计", "机械原理", "工程制图", "机械制造技术", "液压与气压传动", "控制工程基础"],
        "机械设计制造及其自动化": ["机械制图", "理论力学", "材料力学", "机械设计", "机械制造技术", "数控技术", "液压传动", "互换性与测量技术"],
        "车辆工程":            ["汽车构造", "汽车理论", "汽车设计", "发动机原理", "汽车电子", "理论力学", "材料力学", "汽车试验"],
        "机械电子工程":        ["机械设计", "电工电子技术", "传感器与检测", "微机原理", "控制工程", "机电传动控制", "机电系统设计", "PLC原理"],
        "智能制造工程":        ["机械设计", "工业机器人", "传感器技术", "物联网技术", "大数据", "人工智能", "数字孪生", "MES系统"],
        "电气工程及其自动化":  ["电路", "电机学", "电力电子技术", "电力系统分析", "自动控制原理", "高电压技术", "继电保护", "电磁场"],
        "土木工程":            ["理论力学", "材料力学", "结构力学", "土力学", "混凝土结构", "钢结构", "土木工程施工", "工程测量"],
        "建筑学":              ["建筑设计", "建筑构造", "建筑物理", "建筑历史", "城市规划原理", "建筑力学", "建筑结构", "建筑设备"],
        "城乡规划":            ["城市规划原理", "城市设计", "居住区规划", "城市交通", "城市生态", "GIS应用", "城市经济学", "规划CAD"],
        "水利水电工程":        ["水力学", "工程水文学", "水工建筑物", "水利工程施工", "水电站", "土力学", "工程地质", "水资源规划"],
        "测绘工程":            ["测绘学", "GPS原理", "遥感原理", "GIS原理", "大地测量", "工程测量", "摄影测量", "变形监测"],
        "化学工程与工艺":      ["化工原理", "物理化学", "化学反应工程", "化工热力学", "有机化学", "化工工艺", "化工分离工程", "过程控制"],
        "材料科学与工程":      ["材料科学基础", "材料物理", "材料力学", "材料加工", "金属学", "热处理", "材料测试", "复合材料"],
        "能源与动力工程":      ["工程热力学", "流体力学", "传热学", "燃烧学", "制冷原理", "汽轮机", "锅炉原理", "新能源技术"],
        "环境工程":            ["环境工程原理", "水污染控制", "大气污染控制", "固体废物处理", "环境监测", "环境微生物", "环境影响评价", "物理化学"],
        "生物医学工程":        ["生物医学工程导论", "解剖生理学", "生物医学信号处理", "医学图像处理", "生物力学", "生物材料", "医学传感器", "电路分析"],
        "生物工程":            ["生物化学", "微生物学", "分子生物学", "生物反应工程", "生物分离工程", "发酵工程", "基因工程", "酶工程"],
        "食品科学与工程":      ["食品化学", "食品微生物", "食品工艺学", "食品分析", "营养学", "食品安全", "食品机械", "食品工程原理"],
        "制药工程":            ["有机化学", "药物化学", "药剂学", "药理学", "化工原理", "制药工艺", "药物分析", "GMP管理"],
        "交通运输":            ["交通工程学", "交通规划", "路基路面工程", "道路勘测设计", "运输组织", "交通管理与控制", "智能交通", "系统工程"],
        "交通工程":            ["交通工程学", "交通规划", "交通设计", "交通管理与控制", "交通安全", "智能交通", "道路工程", "系统工程"],
        "船舶与海洋工程":      ["船舶原理", "船舶结构力学", "船舶设计", "船舶阻力与推进", "船舶静力学", "海洋工程", "流体力学", "材料力学"],
        "航空航天工程":        ["空气动力学", "飞行力学", "飞行器结构", "推进系统", "飞行控制", "材料力学", "自动控制", "航天器设计"],
        "飞行器设计与工程":    ["空气动力学", "飞行器结构设计", "飞行力学", "飞行器总体设计", "材料力学", "推进系统", "自动控制", "航空材料"],
        "安全工程":            ["安全系统工程", "安全人机工程", "安全管理", "防火防爆", "电气安全", "职业卫生", "应急救援", "安全评价"],
        "工程力学":            ["理论力学", "材料力学", "弹性力学", "结构力学", "流体力学", "计算力学", "振动力学", "实验力学"],
        "工业设计":            ["工业设计概论", "人机工程学", "造型设计", "设计材料", "产品设计", "交互设计", "设计心理学", "计算机辅助设计"],
        "过程装备与控制工程":  ["化工原理", "材料力学", "工程热力学", "过程设备设计", "过程流体机械", "过程控制", "CAD/CAM", "焊接结构"],

        # === 理学 ===
        "数学与应用数学": ["数学分析", "高等代数", "解析几何", "概率论", "常微分方程", "复变函数", "实变函数", "数值分析"],
        "信息与计算科学": ["数学分析", "高等代数", "离散数学", "数值分析", "数据结构", "运筹学", "概率论", "信息论基础"],
        "物理学":          ["力学", "热学", "电磁学", "光学", "原子物理", "理论力学", "电动力学", "量子力学"],
        "应用物理学":      ["力学", "电磁学", "量子力学", "固体物理", "计算物理", "电子技术", "光学", "半导体物理"],
        "化学":            ["无机化学", "有机化学", "分析化学", "物理化学", "结构化学", "仪器分析", "化工原理", "高分子化学"],
        "应用化学":        ["无机化学", "有机化学", "分析化学", "物理化学", "化工原理", "精细化工", "仪器分析", "高分子材料"],
        "生物科学":        ["植物学", "动物学", "微生物学", "生物化学", "分子生物学", "细胞生物学", "遗传学", "生态学"],
        "生物技术":        ["生物化学", "分子生物学", "细胞生物学", "基因工程", "微生物学", "蛋白质工程", "发酵工程", "免疫学"],
        "心理学":          ["普通心理学", "实验心理学", "心理统计", "认知心理学", "发展心理学", "社会心理学", "人格心理学", "变态心理学"],
        "应用心理学":      ["普通心理学", "心理测量", "心理咨询", "社会心理学", "发展心理学", "管理心理学", "临床心理学", "变态心理学"],
        "统计学":          ["数学分析", "高等代数", "概率论", "数理统计", "回归分析", "多元统计", "时间序列", "抽样调查"],
        "应用统计学":      ["概率论", "数理统计", "回归分析", "抽样调查", "统计软件", "多元统计", "时间序列", "非参数统计"],
        "地理科学":        ["自然地理学", "人文地理学", "地图学", "遥感概论", "GIS原理", "气象学", "地质学", "地貌学"],
        "地理信息科学":    ["GIS原理", "遥感数字图像处理", "空间数据库", "地图学", "GPS原理", "空间分析", "WebGIS", "测量学"],
        "大气科学":        ["大气物理学", "天气学", "动力气象学", "气候学", "大气探测", "数值天气预报", "流体力学", "大气化学"],
        "海洋科学":        ["海洋学导论", "物理海洋学", "海洋化学", "海洋生物学", "海洋地质", "海洋调查", "流体力学", "海洋遥感"],

        # === 文学 ===
        "汉语言文学":      ["古代汉语", "现代汉语", "中国古代文学", "中国现当代文学", "外国文学", "文学理论", "语言学概论", "写作"],
        "汉语国际教育":    ["现代汉语", "古代汉语", "语言学概论", "第二语言习得", "对外汉语教学法", "跨文化交际", "中国文化", "英语"],
        "英语":            ["基础英语", "高级英语", "英语听力", "英语口语", "英语写作", "英美文学", "语言学", "翻译理论与实践"],
        "翻译":            ["英汉笔译", "英汉口译", "交替传译", "同声传译", "翻译理论", "高级英语", "语言学", "跨文化交际"],
        "新闻学":          ["新闻学概论", "新闻采访", "新闻写作", "新闻编辑", "新闻评论", "传播学", "新闻摄影", "中国新闻史"],
        "传播学":          ["传播学概论", "媒介研究", "公共关系", "广告学", "社会学", "社会心理学", "市场调查", "新媒体研究"],
        "网络与新媒体":    ["新媒体概论", "网络传播", "数据新闻", "社交媒体", "数字营销", "网页设计", "影视制作", "传播学"],
        "广告学":          ["广告学概论", "广告策划", "广告创意", "市场调查", "广告文案", "品牌管理", "传播学", "消费者行为"],
        "广播电视学":      ["广播电视概论", "电视节目制作", "播音主持", "纪录片创作", "视听语言", "传播学", "新媒体", "节目策划"],

        # === 经济学 ===
        "经济学":          ["微观经济学", "宏观经济学", "政治经济学", "计量经济学", "经济史", "发展经济学", "中级微观", "中级宏观"],
        "金融学":          ["货币银行学", "投资学", "公司金融", "国际金融", "金融市场学", "计量经济学", "宏观经济学", "微观经济学"],
        "金融工程":        ["金融数学", "随机过程", "金融工程", "衍生品定价", "固定收益", "风险管理", "计量经济学", "时间序列"],
        "国际经济与贸易":  ["国际贸易理论", "国际贸易实务", "国际金融", "国际结算", "海关实务", "计量经济学", "宏观经济学", "国际商法"],
        "财政学":          ["财政学", "税收学", "公共预算", "政府会计", "宏观经济学", "微观经济学", "计量经济学", "财政管理"],
        "保险学":          ["保险学", "财产保险", "人身保险", "再保险", "精算学", "风险管理", "金融学", "计量经济学"],
        "投资学":          ["投资学", "证券投资", "公司金融", "金融衍生品", "量化投资", "计量经济学", "宏观经济学", "微观经济学"],
        "经济统计学":      ["概率论与数理统计", "国民经济核算", "计量经济学", "抽样调查", "时间序列", "多元统计", "微观经济学", "宏观经济学"],

        # === 管理学 ===
        "工商管理":        ["管理学原理", "微观经济学", "市场营销", "会计学", "财务管理", "人力资源", "战略管理", "运营管理"],
        "会计学":          ["基础会计", "中级财务会计", "高级财务会计", "成本会计", "管理会计", "审计学", "财务管理", "税法"],
        "财务管理":        ["财务管理", "中级财务会计", "管理会计", "投资学", "金融市场", "公司金融", "成本管理", "审计学"],
        "人力资源管理":    ["人力资源管理", "组织行为学", "劳动经济学", "招聘与选拔", "薪酬管理", "绩效管理", "劳动关系", "管理学"],
        "市场营销":        ["市场营销学", "消费者行为学", "市场调查", "品牌管理", "广告学", "渠道管理", "服务营销", "数字营销"],
        "物流管理":        ["物流学", "供应链管理", "仓储管理", "运输管理", "运筹学", "物流信息系统", "管理学", "生产运作"],
        "信息管理与信息系统": ["管理信息系统", "数据库原理", "数据结构", "系统分析与设计", "ERP原理", "计算机网络", "运筹学", "管理学"],
        "工程管理":        ["工程经济学", "工程项目管理", "土木工程概论", "合同管理", "造价管理", "建设法规", "运筹学", "管理学"],
        "公共事业管理":    ["公共管理学", "公共政策", "社会学", "社会保障", "公共经济学", "行政法", "非营利组织管理", "公共管理"],
        "行政管理":        ["行政管理学", "公共政策", "行政法", "政治学", "公共经济学", "组织行为学", "管理学", "公共部门人力"],
        "旅游管理":        ["旅游学概论", "酒店管理", "旅行社管理", "旅游规划", "旅游市场营销", "旅游经济学", "管理学", "旅游英语"],

        # === 法学 ===
        "法学":            ["法理学", "宪法学", "民法总论", "刑法总论", "行政法", "民事诉讼法", "刑事诉讼法", "商法"],
        "知识产权":        ["知识产权法总论", "专利法", "商标法", "著作权法", "反不正当竞争法", "民法", "行政法", "国际经济法"],
        "政治学与行政学":  ["政治学原理", "西方政治思想史", "中国政治制度", "比较政治", "公共行政学", "国际政治", "行政法", "公共政策"],
        "社会学":          ["社会学概论", "社会研究方法", "西方社会学理论", "社会统计学", "社会心理学", "中国社会", "人类学", "社会分层"],
        "社会工作":        ["社会工作概论", "个案工作", "小组工作", "社区工作", "社会政策", "社会学", "心理学", "社会行政"],

        # === 教育学 ===
        "教育学":          ["教育学原理", "中国教育史", "外国教育史", "教育心理学", "教育研究方法", "课程与教学论", "德育原理", "比较教育"],
        "教育技术学":      ["教育技术学导论", "多媒体技术", "远程教育", "教学设计", "教学系统设计", "数据结构", "人工智能", "学习理论"],
        "学前教育":        ["学前教育学", "学前心理学", "学前卫生学", "幼儿园课程", "学前游戏", "儿童发展", "幼儿舞蹈", "美术"],
        "小学教育":        ["小学教育学", "小学心理学", "小学语文教学法", "小学数学教学法", "班级管理", "课程论", "教学论", "儿童发展"],

        # === 医学 ===
        "临床医学":        ["系统解剖学", "组织胚胎学", "生理学", "生物化学", "病理学", "药理学", "诊断学", "内科学", "外科学", "妇产科学", "儿科学"],
        "口腔医学":        ["口腔解剖生理学", "口腔组织病理学", "口腔材料学", "牙体牙髓病学", "牙周病学", "口腔颌面外科学", "口腔修复学", "口腔正畸学"],
        "中医学":          ["中医基础理论", "中医诊断学", "中药学", "方剂学", "内经", "伤寒论", "金匮要略", "温病学", "中医内科学", "针灸学"],
        "药学":            ["有机化学", "分析化学", "药物化学", "药剂学", "药理学", "药事管理学", "天然药物化学", "药物分析"],
        "护理学":          ["护理学基础", "内科护理学", "外科护理学", "妇产科护理学", "儿科护理学", "急危重症护理", "护理心理学", "护理管理"],
        "预防医学":        ["流行病学", "卫生统计学", "环境卫生学", "营养与食品卫生", "职业卫生", "儿童少年卫生", "毒理学", "社会医学"],

        # === 历史学 ===
        "历史学":          ["中国古代史", "中国近代史", "世界古代史", "世界近代史", "史学概论", "史学史", "考古学", "文献学"],
        "考古学":          ["考古学导论", "田野考古", "考古技术", "文物学", "博物馆学", "中国古代史", "古文字学", "文化遗产保护"],

        # === 艺术学 ===
        "音乐学":          ["基本乐理", "视唱练耳", "和声学", "曲式分析", "中国音乐史", "西方音乐史", "民族音乐学", "音乐美学"],
        "美术学":          ["素描", "色彩", "中外美术史", "透视", "解剖", "艺术概论", "油画/国画", "美学"],
        "视觉传达设计":    ["设计基础", "字体设计", "版式设计", "图形创意", "标志设计", "VI设计", "包装设计", "海报设计"],
        "环境设计":        ["设计基础", "室内设计", "景观设计", "建筑制图", "材料与构造", "家具设计", "照明设计", "公共艺术"],
        "数字媒体艺术":    ["数字影像", "交互设计", "三维建模", "动态图形", "虚拟现实", "游戏设计", "声音设计", "数字绘画"],
    }

    MAJOR_LEVEL_SEEDS: dict[tuple[str, str], list[str]] = {
        # === 工学 ===
        ("计算机科学与技术", "大一"): ["高等数学", "线性代数", "大学物理", "C程序设计", "离散数学"],
        ("计算机科学与技术", "大二"): ["数据结构", "计算机组成原理", "操作系统", "计算机网络", "数字电路", "概率论"],
        ("计算机科学与技术", "大三"): ["编译原理", "数据库系统", "软件工程", "人工智能导论", "算法设计与分析"],
        ("软件工程", "大一"): ["高等数学", "线性代数", "面向对象程序设计", "离散数学", "Python程序设计"],
        ("软件工程", "大二"): ["数据结构", "计算机组成原理", "操作系统", "计算机网络", "数据库系统"],
        ("软件工程", "大三"): ["软件工程概论", "软件测试", "软件项目管理", "软件体系结构", "Web开发技术"],
        ("人工智能", "大一"): ["高等数学", "线性代数", "概率论与数理统计", "Python程序设计", "离散数学"],
        ("人工智能", "大二"): ["数据结构", "机器学习基础", "最优化方法", "数字图像处理", "自然语言处理入门"],
        ("人工智能", "大三"): ["深度学习", "计算机视觉", "强化学习", "知识图谱", "语音识别"],
        ("电子信息工程", "大一"): ["高等数学", "线性代数", "大学物理", "C程序设计", "电路分析"],
        ("电子信息工程", "大二"): ["模拟电子技术", "数字电子技术", "信号与系统", "电磁场", "微机原理"],
        ("电子信息工程", "大三"): ["通信原理", "数字信号处理", "嵌入式系统", "信息论", "DSP技术"],
        ("通信工程", "大一"): ["高等数学", "线性代数", "大学物理", "C程序设计", "电路分析"],
        ("通信工程", "大二"): ["信号与系统", "模拟电子技术", "数字电子技术", "电磁场", "概率论"],
        ("通信工程", "大三"): ["通信原理", "数字信号处理", "移动通信", "光纤通信", "信息论与编码"],
        ("自动化", "大一"): ["高等数学", "线性代数", "大学物理", "C程序设计", "电路"],
        ("自动化", "大二"): ["自动控制原理", "模拟电子技术", "数字电子技术", "微机原理", "传感器技术"],
        ("自动化", "大三"): ["现代控制理论", "电机与拖动", "电力电子技术", "过程控制", "运动控制"],
        ("机械工程", "大一"): ["高等数学", "线性代数", "大学物理", "工程制图", "C程序设计"],
        ("机械工程", "大二"): ["理论力学", "材料力学", "机械原理", "电工电子技术", "工程材料"],
        ("机械工程", "大三"): ["机械设计", "机械制造技术", "液压与气压传动", "控制工程基础", "数控技术"],
        ("土木工程", "大一"): ["高等数学", "线性代数", "大学物理", "画法几何", "工程制图"],
        ("土木工程", "大二"): ["理论力学", "材料力学", "结构力学", "土力学", "工程测量"],
        ("土木工程", "大三"): ["混凝土结构", "钢结构", "土木工程施工", "基础工程", "建筑结构抗震"],
        ("电气工程及其自动化", "大一"): ["高等数学", "线性代数", "大学物理", "C程序设计", "电路"],
        ("电气工程及其自动化", "大二"): ["电机学", "模拟电子技术", "数字电子技术", "电磁场", "信号与系统"],
        ("电气工程及其自动化", "大三"): ["电力电子技术", "电力系统分析", "自动控制原理", "高电压技术", "继电保护"],
        ("化学工程与工艺", "大一"): ["高等数学", "线性代数", "无机化学", "大学物理", "分析化学"],
        ("化学工程与工艺", "大二"): ["有机化学", "物理化学", "化工原理", "化工热力学", "工程制图"],
        ("化学工程与工艺", "大三"): ["化学反应工程", "化工工艺", "化工分离工程", "过程控制", "化工设计"],
        ("材料科学与工程", "大一"): ["高等数学", "线性代数", "无机化学", "大学物理", "C程序设计"],
        ("材料科学与工程", "大二"): ["物理化学", "材料科学基础", "材料力学", "固体物理", "有机化学"],
        ("材料科学与工程", "大三"): ["材料物理", "材料加工", "材料测试", "金属学", "复合材料"],

        # === 理学 ===
        ("数学与应用数学", "大一"): ["数学分析", "高等代数", "解析几何", "C程序设计", "大学物理"],
        ("数学与应用数学", "大二"): ["常微分方程", "概率论", "复变函数", "抽象代数", "数值分析"],
        ("数学与应用数学", "大三"): ["实变函数", "泛函分析", "偏微分方程", "拓扑学", "微分几何"],
        ("物理学", "大一"): ["高等数学", "线性代数", "力学", "热学", "C程序设计"],
        ("物理学", "大二"): ["电磁学", "光学", "数学物理方法", "理论力学", "原子物理"],
        ("物理学", "大三"): ["量子力学", "电动力学", "热力学与统计物理", "固体物理", "计算物理"],
        ("化学", "大一"): ["高等数学", "线性代数", "无机化学", "大学物理", "分析化学"],
        ("化学", "大二"): ["有机化学", "物理化学", "结构化学", "仪器分析", "配位化学"],
        ("化学", "大三"): ["高分子化学", "配位化学", "催化化学", "材料化学", "环境化学"],
        ("生物科学", "大一"): ["高等数学", "植物学", "动物学", "无机化学", "有机化学"],
        ("生物科学", "大二"): ["微生物学", "生物化学", "分子生物学", "遗传学", "细胞生物学"],
        ("生物科学", "大三"): ["生态学", "免疫学", "发育生物学", "神经生物学", "进化生物学"],
        ("统计学", "大一"): ["数学分析", "高等代数", "解析几何", "C程序设计", "概率论"],
        ("统计学", "大二"): ["数理统计", "回归分析", "抽样调查", "随机过程", "多元统计"],
        ("统计学", "大三"): ["时间序列分析", "非参数统计", "贝叶斯统计", "统计计算", "数据挖掘"],

        # === 经济学 ===
        ("经济学", "大一"): ["高等数学", "线性代数", "微观经济学", "政治经济学", "会计学"],
        ("经济学", "大二"): ["宏观经济学", "计量经济学", "统计学", "财政学", "金融学"],
        ("经济学", "大三"): ["博弈论", "发展经济学", "产业经济学", "国际经济学", "经济史"],
        ("金融学", "大一"): ["高等数学", "线性代数", "微观经济学", "政治经济学", "会计学"],
        ("金融学", "大二"): ["宏观经济学", "货币银行学", "计量经济学", "统计学", "金融市场学"],
        ("金融学", "大三"): ["投资学", "公司金融", "国际金融", "风险管理", "金融工程"],
        ("会计学", "大一"): ["高等数学", "管理学", "微观经济学", "基础会计", "经济学"],
        ("会计学", "大二"): ["中级财务会计", "成本会计", "管理会计", "财务管理", "统计学"],
        ("会计学", "大三"): ["高级财务会计", "审计学", "税法", "会计信息系统", "财务报表分析"],

        # === 管理学 ===
        ("工商管理", "大一"): ["管理学原理", "高等数学", "微观经济学", "会计学", "组织行为学"],
        ("工商管理", "大二"): ["市场营销", "财务管理", "人力资源管理", "宏观经济学", "统计学"],
        ("工商管理", "大三"): ["战略管理", "运营管理", "创业学", "供应链管理", "管理信息系统"],
        ("财务管理", "大一"): ["高等数学", "管理学", "微观经济学", "基础会计", "法律基础"],
        ("财务管理", "大二"): ["中级财务会计", "管理会计", "财务管理", "金融市场", "统计学"],
        ("财务管理", "大三"): ["高级财务管理", "投资学", "风险管理", "财务分析", "国际财务管理"],

        # === 文学 ===
        ("汉语言文学", "大一"): ["现代汉语", "古代汉语", "中国古代文学", "写作", "中国文学史"],
        ("汉语言文学", "大二"): ["语言学概论", "中国现当代文学", "外国文学", "文学理论", "比较文学"],
        ("汉语言文学", "大三"): ["古代文论", "西方文论", "文献学", "美学", "应用写作"],
        ("英语", "大一"): ["基础英语", "英语听力", "英语口语", "英语语法", "英语写作"],
        ("英语", "大二"): ["高级英语", "英美文学", "语言学", "翻译理论与实践", "英美概况"],
        ("英语", "大三"): ["学术写作", "交替传译", "语言学专题", "跨文化交际", "第二外语"],

        # === 医学 ===
        ("临床医学", "大一"): ["系统解剖学", "组织胚胎学", "医用化学", "高等数学", "生理学"],
        ("临床医学", "大二"): ["生物化学", "病理学", "药理学", "免疫学", "微生物学"],
        ("临床医学", "大三"): ["诊断学", "内科学", "外科学", "医学影像", "临床基本技能"],
        ("口腔医学", "大一"): ["系统解剖学", "组织胚胎学", "医用化学", "生理学", "生物化学"],
        ("口腔医学", "大二"): ["口腔解剖生理学", "口腔组织病理学", "病理学", "药理学", "免疫学"],
        ("口腔医学", "大三"): ["牙体牙髓病学", "牙周病学", "口腔颌面外科学", "口腔修复学", "口腔材料学"],
        ("药学", "大一"): ["高等数学", "无机化学", "分析化学", "有机化学", "生物化学"],
        ("药学", "大二"): ["物理化学", "药物化学", "药剂学", "药理学", "天然药物化学"],
        ("药学", "大三"): ["药物分析", "药事管理学", "临床药学", "药理实验", "药物设计"],
        ("护理学", "大一"): ["人体解剖学", "生理学", "生物化学", "病理学", "药理学"],
        ("护理学", "大二"): ["护理学基础", "健康评估", "内科护理学", "外科护理学", "护理心理学"],
        ("护理学", "大三"): ["妇产科护理学", "儿科护理学", "急危重症护理", "社区护理", "护理管理"],
    }

    DL_SEEDS: dict[tuple[str, str], list[str]] = {
        ("工学", "大一"): ["高等数学", "线性代数", "大学物理", "C程序设计", "Python程序设计"],
        ("工学", "大二"): ["数据结构", "计算机组成原理", "操作系统", "计算机网络", "数字电路"],
        ("工学", "大三"): ["编译原理", "数据库系统", "软件工程", "人工智能导论", "计算机图形学"],
        ("理学", "大一"): ["高等数学", "线性代数", "力学", "热学", "C程序设计"],
        ("理学", "大二"): ["数学分析", "概率论与数理统计", "电磁学", "光学", "算法设计"],
        ("文学", "大一"): ["现代汉语", "中国文学史", "基础写作", "大学英语", "中国古代文学"],
        ("文学", "大二"): ["语言学概论", "外国文学史", "文学理论", "中国古代文论", "比较文学"],
        ("经济学", "大一"): ["高等数学", "微观经济学", "宏观经济学", "政治经济学", "会计学"],
        ("经济学", "大二"): ["计量经济学", "金融学", "财政学", "统计学", "国际贸易理论"],
        ("管理学", "大一"): ["管理学原理", "微观经济学", "高等数学", "组织行为学", "市场营销"],
        ("管理学", "大二"): ["人力资源管理", "财务管理", "运筹学", "战略管理", "管理信息系统"],
        ("医学", "大一"): ["系统解剖学", "组织胚胎学", "医用化学", "细胞生物学", "高等数学"],
        ("医学", "大二"): ["生理学", "生物化学", "病理学", "药理学", "免疫学"],
        ("医学", "大三"): ["药理学", "病理生理学", "诊断学", "内科学", "外科学"],
    }

    # 1) 优先：按专业+年级匹配
    if major and level:
        key = (major, level)
        if key in MAJOR_LEVEL_SEEDS:
            return {"courses": MAJOR_LEVEL_SEEDS[key]}
    # 2) 其次：按专业兜底（同专业任意年级）
    if major and major in MAJOR_SEEDS:
        return {"courses": MAJOR_SEEDS[major]}
    # 3) 再次：按学科+年级匹配
    key = (discipline, level)
    if key in DL_SEEDS:
        return {"courses": DL_SEEDS[key]}
    # 4) 学科兜底
    for (d, _), courses in DL_SEEDS.items():
        if d == discipline:
            return {"courses": courses}
    return {"courses": DL_SEEDS.get(("工学", "大一"), [])}


def search_majors(discipline: str = "", keyword: str = ""):
    from core.majors import flat_majors, MAJORS_TREE
    if keyword:
        flat = flat_majors(discipline or None, keyword)
        return {"majors": flat[:50]}
    if discipline and discipline in MAJORS_TREE:
        return {"tree": {discipline: MAJORS_TREE[discipline]}}
    return {"tree": MAJORS_TREE}


@router.post("/build")
async def build_profile(user_id: str, message: str):
    agent = ProfileAgent()
    state = AgentState(user_id=user_id, user_message=message)
    await agent.process(state)
    return {"ok": True, "reply": state.get("response", "")}


GENERATE_PROFILE_PROMPT = """你是一个教育评估专家。根据学生的问卷数据，生成学习画像，只返回JSON。

问卷数据：
- 学历层次：{education_level} {education_year}
- 学科门类：{discipline}
- 专业名称：{major}
- 交叉学科：{cross_disciplines}
- 薄弱课程列表：{courses_json}

返回格式：
{{
  "ability_scores": {{
    "知识记忆": 1-10,
    "逻辑推理": 1-10,
    "应用实践": 1-10,
    "信息整合": 1-10,
    "应试能力": 1-10
  }},
  "ability_summary": "一句话综合评价（120字内）",
  "weak_courses": [
    {{
      "name": "课程名",
      "knowledge_points": "薄弱知识点原文",
      "difficulty_types": ["困难类型标签"],
      "impacts": ["影响范围标签"],
      "goal": "学习目标标签",
      "strategies": ["具体学习策略标签，如真题强化、概念精讲等"],
      "course_ability_scores": {{
        "知识记忆": 1-10,
        "逻辑推理": 1-10,
        "应用实践": 1-10,
        "信息整合": 1-10,
        "应试能力": 1-10
      }}
    }}
  ],
  "major": "{major}",
  "grade": "年级",
  "knowledge_base": {{"推断的学科掌握度": 0.0-1.0}},
  "cognitive_style": "视觉型/听觉型/实践型",
  "weak_points": ["综合薄弱点摘要"],
  "learning_goal": "综合学习目标",
  "preferred_format": ["偏好学习方式"]
}}

打分规则：
- 若多门课提到'公式记不住'→知识记忆低
- 若多门课提到'解题没思路'→逻辑推理+应用实践双双降低
- '涉及考试担忧'条目越多→应试能力越低
- 若提到'知识太杂抓不住重点'→信息整合低
- strategy标签选择：短期应试→真题强化、考前冲刺；长期应试→体系构建、专题突破；项目驱动→项目实战、案例驱动；扎实基础→概念精讲、循序渐进
- major 字段必须原样返回问卷中提供的专业名称，不要自行推断或修改
只返回JSON，不要其他内容。"""


async def generate_profile_from_questionnaire(req: QuestionnaireRequest, user_id: str):
    courses_json = json.dumps([
        {
            "name": c.get("name", ""),
            "knowledge_points": c.get("knowledge_points", ""),
            "difficulty_types": c.get("difficulty_types", []),
            "impacts": c.get("impacts", []),
            "goal": c.get("goal", ""),
        }
        for c in req.courses
    ], ensure_ascii=False)

    resp = await chat_completion([
        {"role": "user", "content": GENERATE_PROFILE_PROMPT.format(
            education_level=req.education_level,
            education_year=req.education_year,
            discipline=req.discipline,
            major=req.major or req.discipline,
            cross_disciplines="、".join(req.cross_disciplines) if req.cross_disciplines else "无",
            courses_json=courses_json,
        )}
    ], temperature=0.4)

    raw = resp.choices[0].message.content.strip()
    if raw.startswith("```"):
        raw = raw.strip("`").strip()
        if raw.startswith("json"):
            raw = raw[4:].strip()

    data = json.loads(raw)

    db = SessionLocal()
    try:
        existing = db.query(StudentProfile).filter(
            StudentProfile.user_id == user_id
        ).first()

        if existing:
            saved_focus = {
                "focus_stamina_score": existing.focus_stamina_score,
                "focus_peak_hours": existing.focus_peak_hours,
                "focus_interrupt_rate": existing.focus_interrupt_rate,
                "focus_weekly_avg_min": existing.focus_weekly_avg_min,
            }
            db.delete(existing)
            db.commit()
        else:
            saved_focus = {}

        profile = StudentProfile(
            user_id=user_id,
            major=data.get("major", ""),
            grade=data.get("grade", ""),
            knowledge_base=data.get("knowledge_base", {}),
            cognitive_style=data.get("cognitive_style", ""),
            weak_points=data.get("weak_points", []),
            learning_goal=data.get("learning_goal", ""),
            preferred_format=data.get("preferred_format", []),
            education_level=req.education_level,
            education_year=req.education_year,
            discipline=req.discipline,
            cross_disciplines=req.cross_disciplines,
            ability_scores=data.get("ability_scores", {}),
            weak_courses=data.get("weak_courses", []),
            ability_summary=data.get("ability_summary", ""),
            focus_stamina_score=saved_focus.get("focus_stamina_score"),
            focus_peak_hours=saved_focus.get("focus_peak_hours"),
            focus_interrupt_rate=saved_focus.get("focus_interrupt_rate"),
            focus_weekly_avg_min=saved_focus.get("focus_weekly_avg_min"),
        )
        db.add(profile)
        db.commit()
        db.refresh(profile)

        from services.event_service import emit
        import asyncio as _asyncio
        _asyncio.create_task(emit("profile.updated", {"user_id": user_id}))

        return {
            "ok": True,
            "profile": ProfileResponse.model_validate(profile).model_dump(),
        }
    finally:
        db.close()


@router.post("/rebuild")
async def rebuild_profile(user_id: str):
    db = SessionLocal()
    try:
        old = db.query(StudentProfile).filter(
            StudentProfile.user_id == user_id
        ).first()

        old_profile_data = None
        if old:
            old_profile_data = {
                "major": old.major or "",
                "grade": old.grade or "",
                "knowledge_base": old.knowledge_base or {},
                "cognitive_style": old.cognitive_style or "",
                "weak_points": old.weak_points or [],
                "learning_goal": old.learning_goal or "",
                "preferred_format": old.preferred_format or [],
                "education_level": old.education_level or "",
                "education_year": old.education_year or "",
                "discipline": old.discipline or "",
                "cross_disciplines": old.cross_disciplines or [],
                "ability_scores": old.ability_scores or {},
                "weak_courses": old.weak_courses or [],
                "ability_summary": old.ability_summary or "",
                "focus_stamina_score": old.focus_stamina_score,
                "focus_peak_hours": old.focus_peak_hours,
                "focus_interrupt_rate": old.focus_interrupt_rate,
                "focus_weekly_avg_min": old.focus_weekly_avg_min,
            }

        convs = db.query(Conversation).filter(
            Conversation.user_id == user_id
        ).order_by(Conversation.updated_at.desc()).limit(10).all()

        quiz_records = db.query(QuizRecord).filter(
            QuizRecord.user_id == user_id
        ).order_by(QuizRecord.created_at.desc()).limit(50).all()

        chat_summary_parts = []
        for conv in convs:
            msgs = db.query(ChatMessage).filter(
                ChatMessage.conversation_id == conv.id
            ).order_by(ChatMessage.created_at.asc()).limit(20).all()
            for m in msgs:
                prefix = "用户" if m.role == "user" else "助手"
                chat_summary_parts.append(f"{prefix}: {m.content[:200]}")
        chat_summary = "\n".join(chat_summary_parts[-50:]) if chat_summary_parts else "暂无对话记录"

        quiz_text = "暂无答题记录"
        if quiz_records:
            total = len(quiz_records)
            avg = sum(r.score for r in quiz_records) / total
            quiz_text = f"共{total}次答题，平均正确率{avg:.0%}"

        from models.focus import FocusSession
        from collections import Counter
        from datetime import datetime, timezone, timedelta
        focus_sessions = db.query(FocusSession).filter(
            FocusSession.user_id == user_id
        ).order_by(FocusSession.started_at.desc()).all()
        focus_text = "暂无专注记录"
        if focus_sessions:
            fc_total = len(focus_sessions)
            fc_completed = sum(1 for s in focus_sessions if s.completed)
            fc_min = sum(s.duration_min for s in focus_sessions)
            fc_interrupt = round((fc_total - fc_completed) / fc_total * 100, 1) if fc_total > 0 else 0
            hour_counts = Counter(s.started_at.hour for s in focus_sessions if s.completed)
            fc_peak = sorted([h for h, _ in hour_counts.most_common(3)])
            four_weeks_ago = datetime.now(timezone.utc) - timedelta(weeks=4)
            fc_recent = [s for s in focus_sessions if s.started_at and s.started_at.replace(tzinfo=timezone.utc) >= four_weeks_ago]
            fc_weekly = round(sum(s.duration_min for s in fc_recent) / 4) if fc_recent else 0
            focus_text = json.dumps({
                "总专注次数": fc_total, "完成次数": fc_completed,
                "中断率": f"{fc_interrupt}%", "累计专注分钟": fc_min,
                "周均专注分钟": fc_weekly, "高效时段": fc_peak,
            }, ensure_ascii=False)
            focus_stats_computed = {
                "focus_stamina_score": 8 if fc_weekly > 300 else (5 if fc_weekly > 100 else 2),
                "focus_peak_hours": fc_peak,
                "focus_interrupt_rate": fc_interrupt / 100 if fc_total > 0 else 0,
                "focus_weekly_avg_min": fc_weekly,
            }
        else:
            focus_stats_computed = {}

        prompt = """你是一个学生画像分析专家。根据以下数据综合分析学生，只返回JSON。

旧画像：{old_profile}
对话记录：{chat}
答题统计：{quiz}
专注学习行为：{focus}

返回格式：
{{
  "major": "专业名称",
  "grade": "年级",
  "knowledge_base": {{"学科": 0.0-1.0评分}},
  "cognitive_style": "视觉型/听觉型/实践型",
  "weak_points": ["薄弱知识点"],
  "learning_goal": "学习目标描述",
  "preferred_format": ["偏好资源格式"],
  "education_level": "专科生/本科生/硕士研究生/博士研究生",
  "education_year": "大一/大二/大三/大四/大五/研一/研二/研三/博一/博二及以上",
  "discipline": "哲学/经济学/法学/教育学/文学/历史学/理学/工学/农学/医学/军事学/管理学/艺术学/交叉学科",
  "cross_disciplines": ["交叉学科数组"],
  "ability_scores": {{
    "知识记忆": 1-10,
    "逻辑推理": 1-10,
    "应用实践": 1-10,
    "信息整合": 1-10,
    "应试能力": 1-10
  }},
  "weak_courses": [
    {{
      "name": "课程名",
      "knowledge_points": "薄弱知识点",
      "difficulty_types": ["困难类型"],
      "impacts": ["影响范围"],
      "goal": "学习目标",
      "strategies": ["建议策略"],
      "course_ability_scores": {{
        "知识记忆": 1-10,
        "逻辑推理": 1-10,
        "应用实践": 1-10,
        "信息整合": 1-10,
        "应试能力": 1-10
      }}
    }}
  ],
  "ability_summary": "综合能力简评（含一句专注度分析，120字内）"
}}

规则：
- 旧画像是重要先验，除非新证据强，尽量保留稳定信息
- knowledge_base 基于答题正确率修正
- weak_points 根据答题错误和对话中反复问的概念抽取
- **重要**：每门课的 course_ability_scores 必须根据该课的 difficulty_types 差异化打分，不同课程不能相同
- **重要**：ability_summary 末尾用一句话简要分析专注习惯
- 若信息不足，优先沿用旧画像字段，避免留空
- 只返回JSON，不要其他内容"""

        resp = await chat_completion([
            {"role": "user", "content": prompt.format(
                old_profile=json.dumps(old_profile_data or {}, ensure_ascii=False),
                chat=chat_summary[:3000],
                quiz=quiz_text,
                focus=focus_text[:1500],
            )}
        ], temperature=0.3)

        raw = resp.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.strip("`").strip()
            if raw.startswith("json"):
                raw = raw[4:].strip()

        extracted = json.loads(raw)

        courses = extracted.get("weak_courses") or []
        for c in courses:
            diffs = c.get("difficulty_types") or []
            scores = c.get("course_ability_scores") or {}
            if not scores or all(v == list(scores.values())[0] for v in scores.values() if scores):
                scores = {"知识记忆": 7, "逻辑推理": 7, "应用实践": 7, "信息整合": 7, "应试能力": 6}
            for dt in diffs:
                if "记不住" in dt:
                    scores["知识记忆"] = max(3, (scores.get("知识记忆", 7) or 7) - 1)
                if "没思路" in dt:
                    scores["逻辑推理"] = max(3, (scores.get("逻辑推理", 7) or 7) - 1)
                    scores["应用实践"] = max(3, (scores.get("应用实践", 7) or 7) - 1)
                if "实验" in dt or "代码" in dt:
                    scores["应用实践"] = max(3, (scores.get("应用实践", 7) or 7) - 2)
                if "太杂" in dt:
                    scores["信息整合"] = max(3, (scores.get("信息整合", 7) or 7) - 1)
            import hashlib
            seed = int(hashlib.md5((c.get("name", "") + str(diffs)).encode()).hexdigest()[:4], 16) % 7
            for k in scores:
                scores[k] = max(3, min(10, (scores[k] or 5) + (seed % 4) - 2))
            c["course_ability_scores"] = scores

        merged = {
            "major": extracted.get("major") or (old.major if old else "") or "",
            "grade": extracted.get("grade") or (old.grade if old else "") or "",
            "knowledge_base": extracted.get("knowledge_base") or (old.knowledge_base if old else {}) or {},
            "cognitive_style": extracted.get("cognitive_style") or (old.cognitive_style if old else "") or "",
            "weak_points": extracted.get("weak_points") or (old.weak_points if old else []) or [],
            "learning_goal": extracted.get("learning_goal") or (old.learning_goal if old else "") or "",
            "preferred_format": extracted.get("preferred_format") or (old.preferred_format if old else []) or [],
            "education_level": extracted.get("education_level") or (old.education_level if old else "") or "",
            "education_year": extracted.get("education_year") or (old.education_year if old else "") or "",
            "discipline": extracted.get("discipline") or (old.discipline if old else "") or "",
            "cross_disciplines": extracted.get("cross_disciplines") or (old.cross_disciplines if old else []) or [],
            "ability_scores": extracted.get("ability_scores") or (old.ability_scores if old else {}) or {},
            "weak_courses": extracted.get("weak_courses") or (old.weak_courses if old else []) or [],
            "ability_summary": extracted.get("ability_summary") or (old.ability_summary if old else "") or "",
            "focus_stamina_score": focus_stats_computed.get("focus_stamina_score") or (old.focus_stamina_score if old else None),
            "focus_peak_hours": focus_stats_computed.get("focus_peak_hours") or (old.focus_peak_hours if old else None),
            "focus_interrupt_rate": focus_stats_computed.get("focus_interrupt_rate") if focus_stats_computed.get("focus_interrupt_rate") is not None else (old.focus_interrupt_rate if old else None),
            "focus_weekly_avg_min": focus_stats_computed.get("focus_weekly_avg_min") or (old.focus_weekly_avg_min if old else None),
        }

        if old:
            for key, val in merged.items():
                setattr(old, key, val)
            db.commit()
            db.refresh(old)
            saved = old
        else:
            saved = StudentProfile(user_id=user_id, **merged)
            db.add(saved)
            db.commit()
            db.refresh(saved)

        from services.event_service import emit
        import asyncio as _asyncio
        _asyncio.create_task(emit("profile.updated", {"user_id": user_id}))

        return {
            "ok": True,
            "profile": ProfileResponse.model_validate(saved).model_dump(),
            "data_sources": {
                "conversations_analyzed": len(convs),
                "quiz_records_analyzed": len(quiz_records),
                "focus_sessions_analyzed": len(focus_sessions) if focus_sessions else 0,
                "old_profile_loaded": old is not None,
            },
        }
    finally:
        db.close()

@router.post("/run")
async def run_profile_agent(user_id: str, message: str):
    """通过自然语言对话触发画像智能体更新"""
    agent = ProfileAgent()
    state = AgentState(user_id=user_id, user_message=message)
    await agent.process(state)
    return {"ok": True}


@router.post("")
def create_or_update_profile(req: ProfileCreate, user_id: str, db: Session = Depends(get_db)):
    profile = db.query(StudentProfile).filter(
        StudentProfile.user_id == user_id
    ).first()
    if profile:
        for key, val in req.model_dump(exclude_unset=True).items():
            if val:
                setattr(profile, key, val)
    else:
        profile = StudentProfile(user_id=user_id, **req.model_dump(exclude_unset=True))
        db.add(profile)
    db.commit()
    db.refresh(profile)
    return {"ok": True, "profile": ProfileResponse.model_validate(profile).model_dump()}
