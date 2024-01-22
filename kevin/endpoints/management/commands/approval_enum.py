import hutils


class ApprovalEnum(hutils.TupleEnum):
    """
    新增了一个审批流类型，需要先订阅
    https://open.feishu.cn/document/ukTMukTMukTM/ucDOyUjL3gjM14yN4ITN
    """

    FreeActiveCourses = "E084623A-9FE4-4BC1-8333-A67034B4B4A1", "免费开课审批Code"
    FreeActiveCoursesTest = "E44B0C73-99B6-493E-8C6F-BD445613D4D8", "免费开课审批Code Test"
    RefundCourses = "3CC556E1-ACD0-43BC-88F7-06E14E7223A4", "课程回收申请"
    FreePictureBookLesson = "9FFDD441-E63A-4F90-890E-F47E50F6A477", "绘本课赠课"
    NiuWaBackendAuth = "4BE61AEA-8472-4193-9B8C-C87F1C2986F3", "牛娃后台权限申请"
    MentionDeveloped = "3B79821F-6419-4312-B0B4-6F254A2C10CC", "开发提测"
    MentionDirectorDeveloped = "68CBADE2-FF53-4256-B487-1B8D1C59639B", "开发提测(总监确认)"
    CoursesSubLesson = "6F07FF98-7BED-4A75-9A62-4323988FE631", "课程sublesson全部解锁"
    CreatePromoterAccount = "6DFBBE38-B420-4924-A917-E34E599B960F", "创建推广人账号"


class ApprovalStatusEnum(hutils.TupleEnum):
    PENDING = "PENDING", "进行中"
    APPROVED = "APPROVED", "已通过"
    REJECTED = "REJECTED", "已拒绝"
    CANCELED = "CANCELED", "已取消"
    TRANSFERRED = "TRANSFERRED", "已转交"
    DONE = "DONE", "已完成"


class LessonsLevel(hutils.TupleEnum):
    T1GE = "英语T1", "T1GE"
    T2GE = "英语T2", "T2GE"
    K1GE = "英语K1", "K1GE"
    K2GE = "英语K2", "K2GE"
    K3GE = "英语K3", "K3GE"
    K4GE = "英语K4", "K4GE"
    K5GE = "英语K5", "K5GE"
    K6GE = "英语K6", "K6GE"
    K1MA = "思维K1", "K1MA"
    K2MA = "思维K2", "K2MA"
    K3MA = "思维K3", "K3MA"
    K4MA = "思维K4", "K4MA"
    K5MA = "思维K5", "K5MA"
    K6MA = "思维K6", "K6MA"
    GX01 = "国学-城市", "GX01"
    GX02 = "国学-人物", "GX02"
    GX03 = "国学-故事", "GX03"
    # K1YW = "语文K1", "K1YW"
    # K2YW = "语文K2", "K2YW"
    # K3YW = "语文K3", "K3YW"
    # K4YW = "语文K4", "K4YW"
    # K5YW = "语文K5", "K5YW"
    # K6YW = "语文K6", "K6YW"
    GGYD = "呱呱阅读", "GGYD"
    F1GE = "3.0英语T1", "F1GE"
    F2GE = "3.0英语T2", "F2GE"
    S1GE = "3.0英语K1", "S1GE"
    S2GE = "3.0英语K2", "S2GE"
    S3GE = "3.0英语K3", "S3GE"
    S4GE = "3.0英语K4", "S4GE"
    S5GE = "3.0英语K5", "S5GE"
    S6GE = "3.0英语K6", "S6GE"
    S1GEW = "3.0英语K1双月课", "S1GE_W1-6"
    F2GEW = "3.0英语T2双月课", "F2GE_W1-6"
    LCIX = "趣味拓展课", ["LCIX%03d" % i for i in range(1, 54)]


class PromoterUserType(hutils.TupleEnum):
    EXTERNAL = "1", "外部推手"
    NORMAL = "2", "普通员工"


class CoursesType(hutils.TupleEnum):
    SINGLE = "单个用户开通"
    MULTI = "批量开通"


class CoursesMethod(hutils.TupleEnum):
    PLAN = "规划学习"
    ALL = "全部开通"


class CoursesReason(hutils.TupleEnum):
    TO30 = "2.5送3.0"
    PROMOTER = "推手项目"
    WELFARE = "员工福利"


class CheckOption(hutils.TupleEnum):
    USER = "是否2.5用户", "2.5user"
    FULL = "全匹配校验", "fullCompare"
