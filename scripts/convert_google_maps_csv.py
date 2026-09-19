#!/usr/bin/env python3
import csv, json, re, sys
from pathlib import Path

GENRE_RULES = [
    ('ラーメン', [r'ラーメン',r'らーめん',r'拉麺',r'ramen']),
    ('寿司', [r'寿司',r'鮨',r'すし',r'sushi']),
    ('焼肉', [r'焼肉',r'ホルモン',r'yakiniku',r'korean bbq']),
    ('焼鳥', [r'焼鳥',r'焼き鳥',r'やきとり',r'yakitori']),
    ('カレー', [r'カレー',r'curry']),
    ('そば・うどん', [r'蕎麦',r'そば',r'うどん',r'soba',r'udon']),
    ('中華', [r'中華',r'餃子',r'四川',r'上海',r'北京',r'担々',r'台湾',r'飯店',r'china',r'chinese']),
    ('韓国料理', [r'韓国',r'コリアン',r'サムギョプサル',r'韓式',r'korean']),
    ('イタリアン', [r'イタリア',r'ピザ',r'ピッツァ',r'パスタ',r'trattoria',r'osteria',r'ristorante',r'pizzeria',r'pasta',r'italian']),
    ('フレンチ', [r'フレンチ',r'ビストロ',r'bistro',r'brasserie',r'french']),
    ('スペイン料理', [r'スペイン',r'バル',r'tapas',r'paella',r'spanish']),
    ('タイ料理', [r'タイ料理',r'thai']),
    ('ベトナム料理', [r'ベトナム',r'フォー',r'vietnam']),
    ('インド料理', [r'インド料理',r'ナン',r'タンドリー',r'indian']),
    ('ハンバーガー', [r'ハンバーガー',r'burger']),
    ('とんかつ', [r'とんかつ',r'トンカツ',r'豚カツ']),
    ('天ぷら', [r'天ぷら',r'天麩羅',r'tempura']),
    ('鰻', [r'うなぎ',r'鰻',r'unagi']),
    ('海鮮', [r'海鮮',r'魚介',r'刺身',r'seafood']),
    ('居酒屋', [r'居酒屋',r'izakaya']),
    ('バー', [r'bar\b',r'バー',r'pub\b',r'パブ']),
    ('カフェ・喫茶', [r'カフェ',r'喫茶',r'coffee',r'café',r'cafe']),
    ('スイーツ', [r'ケーキ',r'菓子',r'パフェ',r'アイス',r'gelato',r'ジェラート',r'dessert',r'bakery',r'ベーカリー']),
    ('和食', [r'和食',r'割烹',r'懐石',r'会席',r'日本料理',r'食堂',r'定食']),
]
COMPILED = [(genre,[re.compile(p,re.I) for p in pats]) for genre,pats in GENRE_RULES]

def infer_genre(text):
    for genre, pats in COMPILED:
        if any(p.search(text) for p in pats): return genre
    return '未分類'

def split_tags(value):
    if not value: return []
    return [x.strip().lstrip('#') for x in re.split(r'[,、;；\s]+', value) if x.strip()]

def read_takeout_csv(path):
    path = Path(path)
    with path.open('r', encoding='utf-8-sig', newline='') as f:
        lines = f.readlines()
    header_idx = next((i for i,l in enumerate(lines) if l.startswith('タイトル,')), None)
    if header_idx is None: raise ValueError('「タイトル,メモ,URL,タグ,コメント」のヘッダーが見つかりません。')
    reader = csv.DictReader(lines[header_idx:])
    out = []
    for row in reader:
        name = (row.get('タイトル') or '').strip()
        url = (row.get('URL') or '').strip()
        if not name or not url: continue
        memo = (row.get('メモ') or '').strip()
        comment = (row.get('コメント') or '').strip()
        tags = split_tags((row.get('タグ') or '').strip())
        genre = infer_genre(' '.join([name,memo,comment,*tags]))
        out.append({'name':name,'memo':memo,'url':url,'tags':tags,'comment':comment,'genre':genre})
    return out

def main():
    if len(sys.argv)<2:
        print('Usage: python3 scripts/convert_google_maps_csv.py path/to/list.csv [output.json]'); return 1
    src = Path(sys.argv[1])
    dst = Path(sys.argv[2]) if len(sys.argv)>2 else Path('public/data/restaurants.json')
    items = read_takeout_csv(src)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding='utf-8')
    from collections import Counter
    counts=Counter(x['genre'] for x in items)
    print(f'{len(items)} 件を書き出しました → {dst}')
    for k,v in counts.most_common(): print(f'  {k}: {v}')
    return 0
if __name__=='__main__': raise SystemExit(main())
