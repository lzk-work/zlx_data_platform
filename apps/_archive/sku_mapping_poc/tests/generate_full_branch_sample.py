"""Generate Excel files for the full-branch SKU mapping sample."""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook


BASE = Path(__file__).resolve().parents[1] / "data" / "samples" / "full_branch_case"


def write_xlsx(path: Path, headers: list[object], rows: list[list[object]]) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Sheet1"
    sheet.append(headers)
    for row in rows:
        sheet.append(row)
    workbook.save(path)


def url(source_id: int) -> str:
    return f"https://detail.1688.com/offer/{source_id}.html"


def daily_row(
    platform_sku: str,
    initial_sku: str,
    order_no: str,
    order_time: str,
    source_id: int,
    spec: str,
    remark: str,
    *,
    category: str = "Home",
    code: str = "JT",
    price: int = 30,
    weight_g: float = 250,
) -> list[object]:
    return [
        platform_sku,
        initial_sku,
        order_no,
        "Amazon-US",
        "shop-a",
        order_time,
        f"https://detail.1688.com/offer/{source_id}.html?spm=test",
        spec,
        category,
        code,
        f"https://img.example.com/{platform_sku or 'empty'}.png",
        price,
        weight_g,
        10,
        20,
        30,
        1,
        "White",
        "Plastic",
        "测试中文名",
        remark,
    ]


def main() -> None:
    for subdir in ["input", "source", "state", "output"]:
        (BASE / subdir).mkdir(parents=True, exist_ok=True)

    product_headers = [
        "商品SKU",
        "货源图片链接",
        "货源链接",
        "规格",
        "采购价/￥",
        "重量/g",
        "长/cm",
        "宽/cm",
        "高/cm",
        "颜色",
        "材质",
        "数量",
        "中文报关名",
        "一级类目",
        "类目代号",
        "临时SKU",
        "供应商",
        "备注",
    ]
    product_rows = [
        ["JT_260724_370279", "https://img.example.com/max.png", url(100000), "max-seq", 10, 100, 1, 1, 1, "", "", 1, "测试品", "Home", "JT", "", "", "用于验证当天生成SKU最大序号"],
        ["YS_260725_999999", "https://img.example.com/max-other-day.png", url(100009), "max-other-day", 10, 100, 1, 1, 1, "", "", 1, "测试品", "Home", "YS", "", "", "其他日期大号不影响当天取号"],
        ["SKU_UP_CONS", "https://img.example.com/01.png", url(100001), "spec-01", 11, 101, 11, 21, 31, "White", "Plastic", 1, "白色配件", "Home", "JT", "", "供应商A", "分支1"],
        ["SKU_INIT_UP_WRONG_02", "https://img.example.com/02a.png", url(100021), "old-02", 12, 102, 12, 22, 32, "Black", "Metal", 1, "旧货源", "Home", "JT", "", "供应商A", "分支2初始"],
        ["SKU_MATCH_UP", "https://img.example.com/02b.png", url(100022), "spec-02", 13, 103, 13, 23, 33, "Blue", "Metal", 2, "蓝色配件", "Home", "JT", "", "供应商B", "分支2匹配"],
        ["SKU_INIT_UP_WRONG_03", "https://img.example.com/03a.png", url(100031), "old-03", 14, 104, 14, 24, 34, "", "", 1, "旧货源", "Home", "JT", "", "", "分支3初始"],
        ["SKU_MATCH_NEW", "https://img.example.com/03b.png", url(100032), "spec-03", 15, 105, 15, 25, 35, "Green", "Wood", 3, "绿色配件", "Home", "JT", "", "供应商C", "分支3匹配"],
        ["SKU_INIT_UP_WRONG_04", "https://img.example.com/04a.png", url(100041), "old-04", 16, 106, 16, 26, 36, "", "", 1, "旧货源", "Home", "JT", "", "", "分支4初始"],
        ["SKU_INIT_NEW_CONS", "https://img.example.com/05.png", url(100051), "spec-05", 17, 107, 17, 27, 37, "Red", "Cotton", 4, "红色配件", "Home", "JT", "", "供应商D", "分支5"],
        ["SKU_INIT_NEW_WRONG_06", "https://img.example.com/06a.png", url(100061), "old-06", 18, 108, 18, 28, 38, "", "", 1, "旧货源", "Home", "JT", "", "", "分支6初始"],
        ["SKU_MATCH_UP_06", "https://img.example.com/06b.png", url(100062), "spec-06", 19, 109, 19, 29, 39, "Yellow", "Steel", 5, "黄色配件", "Home", "JT", "", "供应商E", "分支6匹配"],
        ["SKU_INIT_NEW_WRONG_07", "https://img.example.com/07a.png", url(100071), "old-07", 20, 110, 20, 30, 40, "", "", 1, "旧货源", "Home", "JT", "", "", "分支7初始"],
        ["SKU_MATCH_NEW_07", "https://img.example.com/07b.png", url(100072), "spec-07", 21, 111, 21, 31, 41, "Purple", "Paper", 6, "紫色配件", "Home", "JT", "", "供应商F", "分支7匹配"],
        ["SKU_INIT_NEW_WRONG_08", "https://img.example.com/08a.png", url(100081), "old-08", 22, 112, 22, 32, 42, "", "", 1, "旧货源", "Home", "JT", "", "", "分支8初始"],
        ["SKU_EMPTY_MATCH_UP", "https://img.example.com/09.png", url(100091), "spec-09", 23, 113, 23, 33, 43, "Orange", "Glass", 7, "橙色配件", "Home", "JT", "", "供应商G", "分支9"],
        ["SKU_EMPTY_MATCH_NEW", "https://img.example.com/10.png", url(100101), "spec-10", 24, 114, 24, 34, 44, "Gray", "Silicone", 8, "灰色配件", "Home", "JT", "", "供应商H", "分支10"],
        ["SKU_DEDUP_EARLY", "https://img.example.com/dedup1.png", url(100201), "spec-dedup-early", 25, 115, 25, 35, 45, "", "", 1, "去重早单", "Home", "JT", "", "", "重复平台SKU早单"],
        ["SKU_DEDUP_LATE", "https://img.example.com/dedup2.png", url(100202), "spec-dedup-late", 26, 116, 26, 36, 46, "", "", 1, "去重晚单", "Home", "JT", "", "", "重复平台SKU晚单"],
        ["SKU_DUP_A", "https://img.example.com/dup-a.png", url(100888), "spec-dup", 27, 117, 27, 37, 47, "", "", 1, "重复A", "Home", "JT", "", "", "故意重复货源A"],
        ["SKU_DUP_B", "https://img.example.com/dup-b.png", url(100888), "spec-dup", 28, 118, 28, 38, 48, "", "", 1, "重复B", "Home", "JT", "", "", "故意重复货源B"],
    ]
    write_xlsx(BASE / "source" / "商品基础库Excel兼容表.xlsx", product_headers, product_rows)
    write_xlsx(BASE / "source" / "一级类目编码表.xlsx", ["一级类目", "一级类目中文", "code"], [["Home", "家居", "JT"], ["Kitchen", "厨房", "CF"]])

    write_xlsx(
        BASE / "state" / "已上传商品SKU产品表.xlsx",
        ["商品SKU", "首次上传时间", "最后更新时间", "备注"],
        [
            ["SKU_UP_CONS", "2026-07-20 09:00:00", "2026-07-20 09:00:00", "分支1已上传"],
            ["SKU_INIT_UP_WRONG_02", "2026-07-20 09:00:00", "2026-07-20 09:00:00", "分支2初始已上传"],
            ["SKU_MATCH_UP", "2026-07-20 09:00:00", "2026-07-20 09:00:00", "分支2匹配已上传"],
            ["SKU_INIT_UP_WRONG_03", "2026-07-20 09:00:00", "2026-07-20 09:00:00", "分支3初始已上传"],
            ["SKU_INIT_UP_WRONG_04", "2026-07-20 09:00:00", "2026-07-20 09:00:00", "分支4初始已上传"],
            ["SKU_MATCH_UP_06", "2026-07-20 09:00:00", "2026-07-20 09:00:00", "分支6匹配已上传"],
            ["SKU_EMPTY_MATCH_UP", "2026-07-20 09:00:00", "2026-07-20 09:00:00", "分支9匹配已上传"],
        ],
    )
    write_xlsx(
        BASE / "state" / "历史出单平台SKU表.xlsx",
        ["平台SKU", "订单号", "平台渠道", "店铺账号", "首次出单时间", "首次处理时间", "处理批次", "备注"],
        [["PSKU_HIST", "OHIST", "Amazon-US", "shop-a", "2026-07-23 09:00:00", "2026-07-23 10:00:00", "OLD_BATCH", "历史出单跳过"]],
    )
    write_xlsx(
        BASE / "state" / "商品SKU-平台SKU映射关系表.xlsx",
        ["商品SKU", "平台SKU", "绑定时间", "最后更新时间", "绑定来源", "备注"],
        [
            ["SKU_UP_CONS", "OLD_UP_CONS", "2026-07-20 09:00:00", "2026-07-20 09:00:00", "初始导入", "分支1旧平台SKU"],
            ["SKU_MATCH_UP", "OLD_MATCH_UP", "2026-07-20 09:00:00", "2026-07-20 09:00:00", "初始导入", "分支2旧平台SKU"],
            ["SKU_MATCH_UP_06", "OLD_MATCH_UP_06", "2026-07-20 09:00:00", "2026-07-20 09:00:00", "初始导入", "分支6旧平台SKU"],
            ["SKU_EMPTY_MATCH_UP", "OLD_EMPTY_MATCH_UP", "2026-07-20 09:00:00", "2026-07-20 09:00:00", "初始导入", "分支9旧平台SKU"],
        ],
    )

    daily_headers = [
        "平台SKU",
        "初始商品SKU",
        "订单号",
        "平台渠道",
        "店铺账号",
        "出单时间",
        "校正后货源链接",
        "校正后规格",
        "一级类目",
        "类目代号",
        "图片链接",
        "采购价/￥",
        "重量/g",
        "长/cm",
        "宽/cm",
        "高/cm",
        "数量",
        "颜色",
        "材质",
        "中文报关名",
        "备注",
    ]
    daily_rows = [
        daily_row("PSKU_BR01", "SKU_UP_CONS", "O-BR01", "2026-07-24 09:01:00", 100001, "spec-01", "分支1 初始已上传+货源无误->ERP更新"),
        daily_row("PSKU_BR02", "SKU_INIT_UP_WRONG_02", "O-BR02", "2026-07-24 09:02:00", 100022, "spec-02", "分支2 初始已上传+货源有误+匹配已上传->ERP更新"),
        daily_row("PSKU_BR03", "SKU_INIT_UP_WRONG_03", "O-BR03", "2026-07-24 09:03:00", 100032, "spec-03", "分支3 初始已上传+货源有误+匹配未上传->ERP新增"),
        daily_row("PSKU_BR04", "SKU_INIT_UP_WRONG_04", "O-BR04", "2026-07-24 09:04:00", 100042, "spec-04-new", "分支4 初始已上传+货源有误+未匹配->生成新SKU"),
        daily_row("PSKU_BR05", "SKU_INIT_NEW_CONS", "O-BR05", "2026-07-24 09:05:00", 100051, "spec-05", "分支5 初始未上传+货源无误->ERP新增"),
        daily_row("PSKU_BR06", "SKU_INIT_NEW_WRONG_06", "O-BR06", "2026-07-24 09:06:00", 100062, "spec-06", "分支6 初始未上传+货源有误+匹配已上传->ERP更新"),
        daily_row("PSKU_BR07", "SKU_INIT_NEW_WRONG_07", "O-BR07", "2026-07-24 09:07:00", 100072, "spec-07", "分支7 初始未上传+货源有误+匹配未上传->ERP新增"),
        daily_row("PSKU_BR08", "SKU_INIT_NEW_WRONG_08", "O-BR08", "2026-07-24 09:08:00", 100082, "spec-08-new", "分支8 初始未上传+货源有误+未匹配->生成新SKU"),
        daily_row("PSKU_BR09", "", "O-BR09", "2026-07-24 09:09:00", 100091, "spec-09", "分支9 初始为空+匹配已上传->ERP更新"),
        daily_row("PSKU_BR10", "", "O-BR10", "2026-07-24 09:10:00", 100101, "spec-10", "分支10 初始为空+匹配未上传->ERP新增"),
        daily_row("PSKU_BR11", "", "O-BR11", "2026-07-24 09:11:00", 100111, "spec-11-new", "分支11 初始为空+未匹配->生成新SKU"),
        daily_row("PSKU_HIST", "SKU_UP_CONS", "O-HIST-NEW", "2026-07-24 09:12:00", 100111, "ignored-by-history", "历史出单，应跳过且不处理校正信息"),
        daily_row("", "SKU_UP_CONS", "O-EMPTY-PLATFORM", "2026-07-24 09:13:00", 100001, "spec-01", "异常 平台SKU为空"),
        daily_row("PSKU_NO_CAT", "", "O-NOCAT", "2026-07-24 09:14:00", 100121, "spec-no-cat", "异常 缺少类目编码", category="Unknown", code=""),
        daily_row("PSKU_DUP_SOURCE", "SKU_DUP_A", "O-DUP", "2026-07-24 09:15:00", 100888, "spec-dup", "异常 基础库重复货源"),
        daily_row("PSKU_DEDUP", "SKU_DEDUP_LATE", "O-DEDUP-LATE", "2026-07-24 09:30:00", 100202, "spec-dedup-late", "重复平台SKU晚单，应该被忽略"),
        daily_row("PSKU_DEDUP", "SKU_DEDUP_EARLY", "O-DEDUP-EARLY", "2026-07-24 09:00:00", 100201, "spec-dedup-early", "重复平台SKU早单，应该保留"),
    ]
    write_xlsx(BASE / "input" / "每日出单平台SKU输入表.xlsx", daily_headers, daily_rows)
    print(BASE)


if __name__ == "__main__":
    main()
