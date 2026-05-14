from __future__ import annotations

import argparse
from dataclasses import dataclass

from neo4j import GraphDatabase

from app.core.config import settings
from app.graph.pricing_repository import Neo4jPricingRepository
from app.models.pricing import CpuSpecsImportRow


RAW_CPU_ROWS = """
Ryzen 7 5700X\t8 / 16\t3.4 to 4.6 GHz\tSocket AM4\t7 nm\t32 MB\t65 W
Ryzen 5 5500\t6 / 12\t3.6 to 4.2 GHz\tSocket AM4\t7 nm\t16 MB\t65 W
Ryzen 5 3600\t6 / 12\t3.6 to 4.2 GHz\tSocket AM4\t7 nm\t32 MB\t65 W
Ryzen 5 5600\t6 / 12\t3.5 to 4.4 GHz\tSocket AM4\t7 nm\t32 MB\t65 W
Ryzen 9 9950X3D2 Dual Edition\t16 / 32\t4.3 to 5.6 GHz\tSocket AM5\t4 nm\t192 MB\t200 W
Ryzen 7 9800X3D\t8 / 16\t4.7 to 5.2 GHz\tSocket AM5\t4 nm\t96 MB\t120 W
Ryzen 5 5600G\t6 / 12\t3.9 to 4.4 GHz\tSocket AM4\t7 nm\t16 MB\t65 W
Ryzen 7 5700X3D\t8 / 16\t3 to 4.1 GHz\tSocket AM4\t7 nm\t96 MB\t105 W
Ryzen 7 5800X3D\t8 / 16\t3.4 to 4.5 GHz\tSocket AM4\t7 nm\t96 MB\t105 W
Ryzen 7 7800X3D\t8 / 16\t4.2 to 5 GHz\tSocket AM5\t5 nm\t96 MB\t120 W
Ryzen 9 9950X3D\t16 / 32\t4.3 to 5.7 GHz\tSocket AM5\t4 nm\t128 MB\t170 W
Ryzen 7 5825U\t8 / 16\t2 to 4.5 GHz\tSocket FP6\t7 nm\t16 MB\t15 W
Ryzen 5 5600X\t6 / 12\t3.7 to 4.6 GHz\tSocket AM4\t7 nm\t32 MB\t65 W
Ryzen 7 3700X\t8 / 16\t3.6 to 4.4 GHz\tSocket AM4\t7 nm\t32 MB\t65 W
Ryzen 5 5500U\t6 / 12\t2.1 to 4 GHz\tSocket FP6\t7 nm\t8 MB\t15 W
Ryzen 7 5700G\t8 / 16\t3.8 to 4.6 GHz\tSocket AM4\t7 nm\t16 MB\t65 W
Ryzen 5 7520U\t4 / 8\t2.8 to 4.3 GHz\tSocket FT6\t6 nm\t4 MB\t15 W
Ryzen 5 2600\t6 / 12\t3.4 to 3.9 GHz\tSocket AM4\t12 nm\t16 MB\t65 W
Ryzen 5 3500X\t6\t3.6 to 4.1 GHz\tSocket AM4\t7 nm\t32 MB\t65 W
Ryzen 7 5800X\t8 / 16\t3.8 to 4.7 GHz\tSocket AM4\t7 nm\t32 MB\t105 W
Ryzen 5 3400G\t4 / 8\t3.7 to 4.2 GHz\tSocket AM4\t12 nm\t4 MB\t65 W
Ryzen 7 5700U\t8 / 16\t1.8 to 4.3 GHz\tSocket FP6\t7 nm\t8 MB\t15 W
Ryzen 3 3200G\t4\t3.6 to 4 GHz\tSocket AM4\t12 nm\t4 MB\t65 W
Core Ultra 7 270K Plus\t24\t3.7 to 5.5 GHz\tSocket 1851\t3 nm\t36 MB\t125 W
Ryzen 5 5600GT\t6 / 12\t3.6 to 4.6 GHz\tSocket AM4\t7 nm\t16 MB\t65 W
Ryzen 7 7730U\t8 / 16\t2 to 4.5 GHz\tSocket FP6\t7 nm\t16 MB\t15 W
Ryzen AI Max+ 395\t16 / 32\t3 to 5.1 GHz\tSocket FP11\t4 nm\t64 MB\t55 W
Ryzen 7 7735HS\t8 / 16\t3.2 to 4.75 GHz\tSocket FP7\t6 nm\t16 MB\t35 W
Ryzen AI 7 350\t8 / 16\t2 to 5 GHz\tSocket FP8\t4 nm\t8 MB\t28 W
Ryzen 9 5950X\t16 / 32\t3.4 to 4.9 GHz\tSocket AM4\t7 nm\t64 MB\t105 W
Ryzen 5 5500X3D\t6 / 12\t3 to 4 GHz\tSocket AM4\t7 nm\t96 MB\t105 W
Ryzen 5 7500F\t6 / 12\t3.7 to 5 GHz\tSocket AM5\t5 nm\t32 MB\t65 W
Ryzen 5 9600X\t6 / 12\t3.9 to 5.4 GHz\tSocket AM5\t4 nm\t32 MB\t65 W
Ryzen 5 PRO 4650G\t6 / 12\t3.7 to 4.2 GHz\tSocket AM4\t7 nm\t8 MB\t65 W
Ryzen 5 3500U\t4 / 8\t2.1 to 3.7 GHz\tSocket FP5\t12 nm\t4 MB\t15 W
Core Ultra 9 285K\t24\t3.7 to 5.7 GHz\tSocket 1851\t3 nm\t36 MB\t125 W
Ryzen 7 5700\t8 / 16\t3.7 to 4.6 GHz\tSocket AM4\t7 nm\t16 MB\t65 W
Ryzen 7 2700X\t8 / 16\t3.7 to 4.35 GHz\tSocket AM4\t12 nm\t16 MB\t105 W
FX-8350\t8\t4 to 4.2 GHz\tSocket AM3+\t32 nm\t8 MB\t125 W
Ryzen 5 1600\t6 / 12\t3.2 to 3.6 GHz\tSocket AM4\t14 nm\t16 MB\t65 W
Core Ultra X7 358H\t16\t1.9 to 4.8 GHz\tBGA 2540\t3 nm\t18 MB\t25 W
Ryzen 3 7320U\t4 / 8\t2.4 to 4.1 GHz\tSocket FT6\t6 nm\t4 MB\t15 W
Core i5-12400F\t6 / 12\t2.5 to 4.4 GHz\tSocket 1700\t10 nm\t18 MB\t65 W
Ryzen 9 9950X\t16 / 32\t4.3 to 5.7 GHz\tSocket AM5\t4 nm\t64 MB\t170 W
Ryzen 3 2200G\t4\t3.5 to 3.7 GHz\tSocket AM4\t14 nm\t4 MB\t65 W
Ryzen 7 1700\t8 / 16\t3 to 3.7 GHz\tSocket AM4\t14 nm\t16 MB\t65 W
Ryzen 5 4600G\t6 / 12\t3.7 to 4.2 GHz\tSocket AM4\t7 nm\t8 MB\t65 W
Ryzen 7 9700X\t8 / 16\t3.8 to 5.5 GHz\tSocket AM5\t4 nm\t32 MB\t65 W
Ryzen 9 3900X\t12 / 24\t3.8 to 4.6 GHz\tSocket AM4\t7 nm\t64 MB\t105 W
Ryzen AI 9 HX 370\t12 / 24\t2 to 5.1 GHz\tSocket FP8\t4 nm\t16 MB\t28 W
Ryzen 9 5900X\t12 / 24\t3.7 to 4.8 GHz\tSocket AM4\t7 nm\t64 MB\t105 W
FX-9590\t8\t4.7 to 5 GHz\tSocket AM3+\t32 nm\t8 MB\t220 W
Ryzen 5 5625U\t6 / 12\t2.3 to 4.3 GHz\tSocket FP6\t7 nm\t16 MB\t15 W
Ryzen 7 260\t8 / 16\t3.8 to 5.1 GHz\tSocket FP8\t4 nm\t16 MB\t45 W
Ryzen 5 PRO 4650U\t6 / 12\t2.1 to 4 GHz\tSocket FP6\t7 nm\t8 MB\t15 W
Ryzen 5 4500\t6 / 12\t3.6 to 4.1 GHz\tSocket AM4\t7 nm\t8 MB\t65 W
Ryzen 5 3600X\t6 / 12\t3.8 to 4.4 GHz\tSocket AM4\t7 nm\t32 MB\t95 W
Ryzen 7 8845HS\t8 / 16\t3.8 to 5.1 GHz\tSocket FP8\t4 nm\t16 MB\t45 W
Ryzen 5 7600X\t6 / 12\t4.7 to 5.3 GHz\tSocket AM5\t5 nm\t32 MB\t105 W
Ryzen 5 PRO 5650U\t6 / 12\t2.3 to 4.2 GHz\tSocket FP6\t7 nm\t16 MB\t15 W
Ryzen 5 2400G\t4 / 8\t3.6 to 3.9 GHz\tSocket AM4\t14 nm\t4 MB\t65 W
Ryzen 7 9850X3D\t8 / 16\t4.7 to 5.6 GHz\tSocket AM5\t4 nm\t96 MB\t120 W
Ryzen Threadripper PRO 9995WX\t96 / 192\t2.5 to 5.4 GHz\tSocket sTR5\t4 nm\t384 MB\t350 W
FX-6300\t6\t3.5 to 4.1 GHz\tSocket AM3+\t32 nm\t8 MB\t95 W
Ryzen 5 2600X\t6 / 12\t3.6 to 4.25 GHz\tSocket AM4\t12 nm\t16 MB\t95 W
Core i5-9400F\t6\t2.9 to 4.1 GHz\tSocket 1151\t14 nm\t9 MB\t65 W
Core i5-10400\t6 / 12\t2.9 to 4.3 GHz\tSocket 1200\t14 nm\t12 MB\t65 W
Ryzen 7 4800H\t8 / 16\t2.9 to 4.2 GHz\tSocket FP6\t7 nm\t8 MB\t45 W
Ryzen 7 7700\t8 / 16\t3.8 to 5.3 GHz\tSocket AM5\t5 nm\t32 MB\t65 W
Ryzen 5 4500U\t6\t2.3 to 4 GHz\tSocket FP6\t7 nm\t8 MB\t15 W
Core Ultra X9 388H\t16\t2.1 to 5.1 GHz\tBGA 2540\t3 nm\t18 MB\t25 W
Ryzen 5 7600\t6 / 12\t3.8 to 5.1 GHz\tSocket AM5\t5 nm\t32 MB\t65 W
Core 2 Duo E8400\t2\t3 GHz\tSocket 775\t45 nm\tN/A\t65 W
Core i5-10400F\t6 / 12\t2.9 to 4.3 GHz\tSocket 1200\t14 nm\t12 MB\t65 W
Ryzen 7 6800H\t8 / 16\t3.2 to 4.7 GHz\tSocket FP7\t6 nm\t16 MB\t45 W
Ryzen 7 5800H\t8 / 16\t3.2 to 4.4 GHz\tSocket FP6\t7 nm\t16 MB\t45 W
Core i3-10100\t4 / 8\t3.6 to 4.3 GHz\tSocket 1200\t14 nm\t6 MB\t65 W
Ryzen 7 250\t8 / 16\t3.3 to 5.1 GHz\tSocket FP8\t4 nm\t16 MB\t28 W
Core i5-14400F\t10 / 16\t2.5 to 4.7 GHz\tSocket 1700\t10 nm\t20 MB\t65 W
Core i9-14900K\t24 / 32\t3.2 to 6 GHz\tSocket 1700\t10 nm\t36 MB\t125 W
Core Ultra 7 255H\t16\t2 to 5.1 GHz\tBGA 2049\t3 nm\t24 MB\t28 W
Core i7-3770\t4 / 8\t3.4 to 3.9 GHz\tSocket 1155\t22 nm\t8 MB\t77 W
Core i9-14900HX\t24 / 32\t2.2 to 5.8 GHz\tBGA 1964\t10 nm\t36 MB\t55 W
Core Ultra 9 275HX\t24\t2.7 to 5.4 GHz\tBGA 2114\t3 nm\t36 MB\t55 W
Core i5-13420H\t8 / 12\t2.1 to 4.6 GHz\tBGA 1744\t10 nm\t12 MB\t45 W
Ryzen 3 3100\t4 / 8\t3.6 to 3.9 GHz\tSocket AM4\t7 nm\t16 MB\t65 W
Ryzen 5 PRO 3500U\t4 / 8\t2.1 to 3.7 GHz\tSocket FP5\t12 nm\t4 MB\t15 W
Ryzen 5 1400\t4 / 8\t3.2 to 3.4 GHz\tSocket AM4\t14 nm\t8 MB\t65 W
Ryzen 5 7535HS\t6 / 12\t3.3 to 4.55 GHz\tSocket FP7\t6 nm\t16 MB\t35 W
Ryzen 7 3800X\t8 / 16\t3.9 to 4.5 GHz\tSocket AM4\t7 nm\t32 MB\t105 W
Core i7-10700\t8 / 16\t2.9 to 4.8 GHz\tSocket 1200\t14 nm\t16 MB\t65 W
Processor N100\t4\t0.1 to 3.4 GHz\tBGA 1264\t10 nm\t6 MB\t6 W
Ryzen 5 4600H\t6 / 12\t3 to 4 GHz\tSocket FP6\t7 nm\t8 MB\t45 W
Core Ultra 7 265K\t20\t3.9 to 5.5 GHz\tSocket 1851\t3 nm\t30 MB\t125 W
Processor N150\t4\t0.1 to 3.6 GHz\tBGA 1264\t10 nm\t6 MB\t6 W
Ryzen 3 1200\t4\t3.1 to 3.4 GHz\tSocket AM4\t14 nm\t8 MB\t65 W
Core i7-4790K\t4 / 8\t4 to 4.4 GHz\tSocket 1150\t22 nm\t8 MB\t88 W
Core i7-6700\t4 / 8\t3.4 to 4 GHz\tSocket 1151\t14 nm\t8 MB\t65 W
Core i7-8700\t6 / 12\t3.2 to 4.6 GHz\tSocket 1151\t14 nm\t12 MB\t65 W
Core i7-7700\t4 / 8\t3.6 to 4.2 GHz\tSocket 1151\t14 nm\t8 MB\t65 W
""".strip()


@dataclass(frozen=True)
class ParsedRow:
    name: str
    cores_threads: str
    clock: str
    socket: str
    process: str
    l3_cache: str
    tdp: str


def parse_rows() -> list[CpuSpecsImportRow]:
    rows: list[CpuSpecsImportRow] = []
    for raw_line in RAW_CPU_ROWS.splitlines():
        parts = raw_line.split("\t")
        if len(parts) != 7:
            raise ValueError(f"Unexpected CPU row shape: {raw_line}")
        row = ParsedRow(*[part.strip() for part in parts])
        rows.append(
            CpuSpecsImportRow(
                name=row.name,
                cores_threads=row.cores_threads,
                clock=row.clock,
                socket=row.socket.removeprefix("Socket ").strip(),
                process=row.process,
                l3_cache=row.l3_cache,
                tdp=row.tdp,
            )
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Import pasted CPU spec rows into Product nodes.")
    parser.add_argument("--live", action="store_true", help="Mutate Neo4j. Without this flag, runs dry-run only.")
    args = parser.parse_args()

    rows = parse_rows()
    dry_run = not args.live

    driver = GraphDatabase.driver(settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password))
    try:
        response = Neo4jPricingRepository(driver).import_cpu_specs(
            rows=rows,
            source_name="TechPowerUp CPU Database",
            dry_run=dry_run,
        )
    finally:
        driver.close()

    print(
        f"dry_run={response.dry_run} imported_count={response.imported_count} "
        f"skipped_count={response.skipped_count} ignored_fields={','.join(response.ignored_fields)}"
    )
    if response.products:
        first = response.products[0]
        print(f"first_product={first.name} canonical_key={first.canonical_key}")


if __name__ == "__main__":
    main()
