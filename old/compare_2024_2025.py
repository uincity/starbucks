import os
import re
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns


SIDO_NAMES = [
    '서울특별시','부산광역시','대구광역시','인천광역시','광주광역시','대전광역시','울산광역시',
    '세종특별자치시','경기도','강원도','충청북도','충청남도','전라북도','전라남도','경상북도','경상남도','제주특별자치도'
]
SIDO_PATTERN = re.compile('|'.join(map(re.escape, SIDO_NAMES)))
ABBREV_MAP = {
    '서울': '서울특별시', '부산': '부산광역시', '대구': '대구광역시', '인천': '인천광역시',
    '광주': '광주광역시', '대전': '대전광역시', '울산': '울산광역시', '세종': '세종특별자치시',
    '제주': '제주특별자치도'
}
ROAD_SUFFIXES = ('로', '길', '대로', '번길')


def split_address(address):
    if pd.isna(address):
        return ["", "", ""]
    addr = str(address).strip()
    # 1) Try to find an explicit 시도 name anywhere in the string
    m = SIDO_PATTERN.search(addr)
    if m:
        sido = m.group(0)
        rest = addr[m.end():].strip()
        rest_tokens = rest.split()
        sigungu = rest_tokens[0] if len(rest_tokens) >= 1 else ""
        road = " ".join(rest_tokens[1:]) if len(rest_tokens) >= 2 else ""
        return [sido, sigungu, road]
    # 2) Abbreviation at start (e.g., 대구 북구 ...)
    for abbr, full in ABBREV_MAP.items():
        if addr.startswith(abbr):
            rest = addr[len(abbr):].strip()
            rest_tokens = rest.split()
            sigungu = rest_tokens[0] if len(rest_tokens) >= 1 else ""
            road = " ".join(rest_tokens[1:]) if len(rest_tokens) >= 2 else ""
            return [full, sigungu, road]
    # 3) Generic pattern: first token that ends with 시 or 도
    tokens = addr.split()
    for i, tok in enumerate(tokens):
        if tok.endswith('시') or tok.endswith('도'):
            sido_guess = tok
            # Map abbreviations like 대구시 -> 대구광역시
            base = tok.replace('시', '')
            if base in ABBREV_MAP:
                sido_guess = ABBREV_MAP[base]
            rest_tokens = tokens[i+1:]
            sigungu = rest_tokens[0] if len(rest_tokens) >= 1 else ""
            road = " ".join(rest_tokens[1:]) if len(rest_tokens) >= 2 else ""
            return [sido_guess, sigungu, road]
    # 4) Fallback to positional split but avoid roads as 시도
    parts = addr.split()
    if len(parts) >= 1 and parts[0].endswith(ROAD_SUFFIXES):
        # if first token is a road name, leave sido empty; try to set 시군 as first token
        if len(parts) >= 3:
            return ["", parts[0], " ".join(parts[1:])]
        if len(parts) == 2:
            return ["", parts[0], parts[1]]
        return ["", parts[0], ""]
    if len(parts) >= 3:
        return [parts[0], parts[1], " ".join(parts[2:])]
    if len(parts) == 2:
        return [parts[0], parts[1], ""]
    if len(parts) == 1:
        return [parts[0], "", ""]
    return ["", "", ""]


def load_and_prepare(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {path}")
    df = pd.read_excel(path)
    # Always recompute parsing from 주소 to avoid stale/wrong existing values
    address_parts = df['주소'].apply(split_address)
    df['시도'] = [p[0] for p in address_parts]
    df['시군'] = [p[1] for p in address_parts]
    df['도로명'] = [p[2] for p in address_parts]
    # Final normalization: ensure standardized full names for metros
    def normalize_sido(s):
        s = str(s).strip()
        if s in ABBREV_MAP:
            return ABBREV_MAP[s]
        base = s.replace('시', '')
        if base in ABBREV_MAP:
            return ABBREV_MAP[base]
        return s
    df['시도'] = df['시도'].apply(normalize_sido)
    return df


def aggregate_by_sido(df: pd.DataFrame) -> pd.Series:
    # Normalize 시도 (strip spaces)
    s = df['시도'].fillna('').astype(str).str.strip()
    return s.value_counts().sort_index()


def align_indexes(s24: pd.Series, s25: pd.Series):
    all_index = sorted(set(s24.index).union(set(s25.index)))
    s24a = s24.reindex(all_index).fillna(0).astype(int)
    s25a = s25.reindex(all_index).fillna(0).astype(int)
    return s24a, s25a


def save_comparison_excel(s24: pd.Series, s25: pd.Series, diff: pd.Series, out_path: str):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    df_out = pd.DataFrame({
        '시도': s24.index,
        '매장수_2024': s24.values,
        '매장수_2025': s25.values,
        '증감(25-24)': diff.values,
    })
    # 안전한 증감률 계산 (2024가 0이면 NaN)
    s24_float = df_out['매장수_2024'].astype(float)
    denom = s24_float.copy()
    denom = denom.mask(denom == 0)
    pct = (df_out['증감(25-24)'].astype(float) / denom) * 100
    df_out['증감률%'] = pct.round(2)
    df_out.to_excel(out_path, index=False)


def plot_comparison(s24: pd.Series, s25: pd.Series, diff: pd.Series, img_path_base: str):
    plt.rcParams['font.family'] = 'Malgun Gothic'
    plt.rcParams['axes.unicode_minus'] = False
    os.makedirs(os.path.dirname(img_path_base), exist_ok=True)

    idx = s24.index
    df_plot = pd.DataFrame({'2024': s24.astype(int).values, '2025': s25.astype(int).values}, index=idx)

    plt.figure(figsize=(14, 7))
    ax = df_plot.plot(kind='bar', figsize=(14, 7), color=['#7fb3d5', '#f5b7b1'], edgecolor='black')
    plt.title('시도별 스타벅스 매장 수: 2024 vs 2025')
    plt.xlabel('시도')
    plt.ylabel('매장 수')
    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()
    out1 = img_path_base + '_시도별_막대.png'
    plt.savefig(out1, dpi=300, bbox_inches='tight')
    plt.close()

    # Difference chart
    plt.figure(figsize=(14, 6))
    diff_int = diff.astype(int)
    colors = ['#2ecc71' if v >= 0 else '#e74c3c' for v in diff_int.values]
    ax = diff_int.plot(kind='bar', color=colors, edgecolor='black')
    plt.title('시도별 증감 (2025 - 2024)')
    plt.xlabel('시도')
    plt.ylabel('증감 수')
    plt.axhline(0, color='black', linewidth=0.8)
    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()
    out2 = img_path_base + '_시도별_증감.png'
    plt.savefig(out2, dpi=300, bbox_inches='tight')
    plt.close()

    return out1, out2


def main():
    file_2024 = './data/startbucks_store_list_20240706.xlsx'
    file_2025 = './startbucks_store_list_20250827.xlsx'

    df24 = load_and_prepare(file_2024)
    df25 = load_and_prepare(file_2025)

    s24_raw = aggregate_by_sido(df24)
    s25_raw = aggregate_by_sido(df25)
    s24, s25 = align_indexes(s24_raw, s25_raw)
    diff = s25 - s24

    # Save table
    out_xlsx = './data/스타벅스_시도비교_2024_vs_2025.xlsx'
    save_comparison_excel(s24, s25, diff, out_xlsx)

    # Plots
    img_base = './data/스타벅스_시도비교_2024vs2025'
    img_paths = plot_comparison(s24, s25, diff, img_base)

    print('✅ 비교 완료:')
    print(f'  - 비교표: {out_xlsx}')
    print(f'  - 시각화: {img_paths[0]}')
    print(f'  - 시각화: {img_paths[1]}')


if __name__ == '__main__':
    main()


