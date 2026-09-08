"""Report readers and reorder calculations adapted from the supplied app.
No database, UI, network or OCR imports. Arabic report columns are retained.
"""
from __future__ import annotations
import io
import re
import unicodedata
import pandas as pd

def normalize_item_name(value):
    """Normalize Ameen item names without changing the displayed Arabic text."""
    text = unicodedata.normalize('NFKC', str(value or ''))
    text = text.replace('"', '').replace("'", '')
    return re.sub('\\s+', ' ', text).strip().casefold()

def normalize_item_code(value):
    if pd.isna(value):
        return ''
    text = str(value).strip()
    return text[:-2] if text.endswith('.0') else text

def split_movement_item(value):
    """Split codes such as SG05LP3-EU-SM2-اسم المادة safely."""
    text = str(value or '').strip()
    match = re.match('^\\s*(.*?)\\s*-\\s*(?=[\\u0600-\\u06FF])(.+)$', text)
    if match:
        return (normalize_item_code(match.group(1)), match.group(2).strip())
    return ('', text)

def read_stock_report(file_bytes):
    """Read both the original 2-column report and older code/name/qty reports."""
    excel = pd.ExcelFile(io.BytesIO(file_bytes))
    for sheet_name in excel.sheet_names:
        for header_row in (0, 1, 2):
            candidate = pd.read_excel(io.BytesIO(file_bytes), sheet_name=sheet_name, header=header_row, dtype=object)
            columns = {str(column).strip(): column for column in candidate.columns}
            name_col = next((columns[key] for key in columns if 'اسم المادة' in key), None)
            qty_col = next((columns[key] for key in columns if key == 'الكمية'), None)
            code_col = next((columns[key] for key in columns if 'رمز المادة' in key), None)
            if name_col is None or qty_col is None:
                continue
            result = pd.DataFrame({'رمز المادة': candidate[code_col].map(normalize_item_code) if code_col is not None else '', 'اسم المادة': candidate[name_col].astype(str).str.strip('"'), 'الكمية': pd.to_numeric(candidate[qty_col], errors='coerce').fillna(0)})
            result = result[candidate[name_col].notna() & result['اسم المادة'].astype(str).str.strip().ne('')].copy()
            result['مفتاح المطابقة'] = result['اسم المادة'].map(normalize_item_name)
            result = result.reset_index(drop=True)
            base_keys = result.apply(lambda row: f"CODE:{normalize_item_code(row['رمز المادة'])}" if normalize_item_code(row['رمز المادة']) else f"NAME:{row['مفتاح المطابقة']}", axis=1)
            duplicate_number = base_keys.groupby(base_keys).cumcount()
            result['مفتاح المخزون'] = [base_key if number == 0 else f'{base_key}#{number + 1}' for base_key, number in zip(base_keys, duplicate_number)]
            return result
    raise ValueError('لم يتم العثور على أعمدة اسم المادة والكمية في تقرير الجرد.')

def read_movement_report(file_bytes):
    """Read the Ameen item-movement report by its stable column positions."""
    excel = pd.ExcelFile(io.BytesIO(file_bytes))
    sheet_name = next((name for name in excel.sheet_names if 'حركة' in str(name)), excel.sheet_names[0])
    raw = pd.read_excel(io.BytesIO(file_bytes), sheet_name=sheet_name, header=1)
    if raw.shape[1] < 9:
        raise ValueError('تقرير حركة المادة لا يحتوي على أعمدة الإدخال والإخراج المطلوبة.')
    parsed_items = raw.iloc[:, 0].map(split_movement_item)
    movement = pd.DataFrame({'رمز المادة': parsed_items.map(lambda item: item[0]), 'اسم المادة': parsed_items.map(lambda item: item[1]), 'التاريخ': pd.to_datetime(raw.iloc[:, 1], errors='coerce'), 'المرجع': raw.iloc[:, 2].fillna('').astype(str).str.strip(), 'الزبون': raw.iloc[:, 3].fillna('').astype(str).str.strip(), 'إدخال': pd.to_numeric(raw.iloc[:, 4], errors='coerce').fillna(0), 'إخراج': pd.to_numeric(raw.iloc[:, 6], errors='coerce').fillna(0), 'الرصيد': pd.to_numeric(raw.iloc[:, 8], errors='coerce'), 'المستخدم': raw.iloc[:, 10].fillna('').astype(str).str.strip() if raw.shape[1] > 10 else '', 'بيان': raw.iloc[:, 13].fillna('').astype(str).str.strip() if raw.shape[1] > 13 else ''})
    movement = movement[movement['التاريخ'].notna()].copy()
    movement['مفتاح المطابقة'] = movement['اسم المادة'].map(normalize_item_name)
    return movement.reset_index(drop=True)

def enrich_stock_codes(stock_df, movement_df):
    stock = stock_df.copy()
    if movement_df is None or movement_df.empty:
        return stock
    codes = movement_df[movement_df[COL_CODE].ne("")].groupby(COL_MATCH)[COL_CODE].agg(lambda x: sorted(set(x)))
    mapping = {k: values[0] for k, values in codes.items() if len(values) == 1}
    missing = stock[COL_CODE].fillna("").astype(str).str.strip().eq("")
    stock.loc[missing, COL_CODE] = stock.loc[missing, COL_MATCH].map(mapping).fillna("")
    return stock


def build_inventory_analysis(stock_df, movement_df, lead_days, safety_days, slow_days, demand_window_days=90, review_days=30, purchase_prefixes=None):
    """Build a purchase-aware reorder plan from demand, stock and supply history."""
    if movement_df is None or movement_df.empty:
        return pd.DataFrame()
    movement_df = movement_df.copy()
    movement_df['التاريخ'] = pd.to_datetime(movement_df['التاريخ'], errors='coerce')
    movement_df = movement_df[movement_df['التاريخ'].notna()].copy()
    end_date = movement_df['التاريخ'].max().normalize()
    demand_window_days = max(7, int(demand_window_days))
    review_days = max(1, int(review_days))
    recent_start = end_date - pd.Timedelta(days=demand_window_days - 1)
    prior_end = recent_start - pd.Timedelta(days=1)
    prior_start = prior_end - pd.Timedelta(days=demand_window_days - 1)
    purchase_prefixes = tuple(str(p).strip() for p in (purchase_prefixes if purchase_prefixes is not None else ("إد.م. م. م.",)) if str(p).strip())
    grouped = movement_df.groupby('مفتاح المطابقة', as_index=False).agg(**{'رمز الحركة': ('رمز المادة', 'first'), 'اسم الحركة': ('اسم المادة', 'first'), 'إجمالي الإدخال': ('إدخال', 'sum'), 'إجمالي الإخراج': ('إخراج', 'sum'), 'عدد الحركات': ('التاريخ', 'count'), 'آخر حركة': ('التاريخ', 'max')})
    last_out = movement_df[movement_df['إخراج'] > 0].groupby('مفتاح المطابقة')['التاريخ'].max()
    grouped['آخر إخراج'] = grouped['مفتاح المطابقة'].map(last_out)
    recent_out = movement_df[(movement_df['إخراج'] > 0) & (movement_df['التاريخ'] >= recent_start) & (movement_df['التاريخ'] < end_date + pd.Timedelta(days=1))].groupby('مفتاح المطابقة')['إخراج'].sum()
    prior_out = movement_df[(movement_df['إخراج'] > 0) & (movement_df['التاريخ'] >= prior_start) & (movement_df['التاريخ'] < recent_start)].groupby('مفتاح المطابقة')['إخراج'].sum()
    grouped[f'خروج آخر {demand_window_days} يوم'] = grouped['مفتاح المطابقة'].map(recent_out).fillna(0)
    grouped['خروج الفترة السابقة'] = grouped['مفتاح المطابقة'].map(prior_out).fillna(0)
    reference = movement_df['المرجع'].fillna('').astype(str).str.strip()
    if purchase_prefixes:
        purchase_mask = (movement_df['إدخال'] > 0) & reference.str.startswith(purchase_prefixes)
    else:
        purchase_mask = pd.Series(False, index=movement_df.index)
    purchases = movement_df[purchase_mask].copy()
    if not purchases.empty:
        purchases['يوم الشراء'] = purchases['التاريخ'].dt.normalize()
        purchase_daily = purchases.groupby(['مفتاح المطابقة', 'يوم الشراء'], as_index=False)['إدخال'].sum().sort_values(['مفتاح المطابقة', 'يوم الشراء'])
        purchase_summary_rows = []
        for item_key, item_purchases in purchase_daily.groupby('مفتاح المطابقة'):
            unique_dates = item_purchases['يوم الشراء'].sort_values()
            gaps = unique_dates.diff().dt.days.dropna()
            last_row = item_purchases.iloc[-1]
            purchase_summary_rows.append({'مفتاح المطابقة': item_key, 'آخر شراء/توريد': last_row['يوم الشراء'], 'كمية آخر شراء/توريد': float(last_row['إدخال']), 'عدد مرات الشراء/التوريد': int(len(item_purchases)), 'متوسط فترة التوريد': float(gaps.mean()) if not gaps.empty else float('nan')})
        purchase_summary = pd.DataFrame(purchase_summary_rows)
        grouped = grouped.merge(purchase_summary, on='مفتاح المطابقة', how='left')
    else:
        grouped['آخر شراء/توريد'] = pd.NaT
        grouped['كمية آخر شراء/توريد'] = 0.0
        grouped['عدد مرات الشراء/التوريد'] = 0
        grouped['متوسط فترة التوريد'] = float('nan')
    stock_view = stock_df[['مفتاح المطابقة', 'رمز المادة', 'اسم المادة', 'الكمية']].copy()
    analysis = stock_view.merge(grouped, on='مفتاح المطابقة', how='left')
    analysis['رمز المادة'] = analysis['رمز المادة'].where(analysis['رمز المادة'].astype(str).str.strip().ne(''), analysis['رمز الحركة']).fillna('')
    numeric_columns = ('إجمالي الإدخال', 'إجمالي الإخراج', 'عدد الحركات', f'خروج آخر {demand_window_days} يوم', 'خروج الفترة السابقة', 'كمية آخر شراء/توريد', 'عدد مرات الشراء/التوريد')
    for column in numeric_columns:
        analysis[column] = pd.to_numeric(analysis[column], errors='coerce').fillna(0)
    recent_column = f'خروج آخر {demand_window_days} يوم'
    analysis['الخروج اليومي الحديث'] = analysis[recent_column] / demand_window_days
    analysis['متوسط الخروج اليومي'] = analysis['الخروج اليومي الحديث']
    recent_rate = analysis[recent_column] / demand_window_days
    prior_rate = analysis['خروج الفترة السابقة'] / demand_window_days
    trend_ratio = recent_rate / prior_rate.replace(0, float("nan"))
    analysis['اتجاه الطلب'] = 'مستقر'
    analysis.loc[(prior_rate <= 0) & (recent_rate > 0), 'اتجاه الطلب'] = 'صاعد'
    analysis.loc[trend_ratio >= 1.25, 'اتجاه الطلب'] = 'صاعد'
    analysis.loc[(trend_ratio <= 0.75) & (recent_rate > 0), 'اتجاه الطلب'] = 'هابط'
    analysis.loc[recent_rate <= 0, 'اتجاه الطلب'] = 'بدون طلب حديث'
    demand = analysis['إجمالي الإخراج'].sort_values(ascending=False)
    total_demand = demand.sum()
    if total_demand > 0:
        cumulative_before = demand.cumsum().shift(fill_value=0) / total_demand
        abc = pd.Series('بطيئة', index=demand.index)
        abc.loc[cumulative_before < 0.95] = 'متوسطة'
        abc.loc[cumulative_before < 0.8] = 'سريعة'
        analysis['سرعة الحركة'] = abc.reindex(analysis.index)
    else:
        analysis['سرعة الحركة'] = 'بدون حركة'
    analysis.loc[analysis['إجمالي الإخراج'] <= 0, 'سرعة الحركة'] = 'بدون حركة'
    analysis['أيام منذ آخر خروج'] = (end_date.normalize() - pd.to_datetime(analysis['آخر إخراج'])).dt.days
    analysis['أيام منذ آخر شراء/توريد'] = (end_date - pd.to_datetime(analysis['آخر شراء/توريد'])).dt.days
    analysis['تغطية المخزون بالأيام'] = (analysis['الكمية'] / recent_rate.replace(0, float('nan'))).clip(lower=0).astype(float).round(1)
    analysis['مخزون الأمان'] = (recent_rate * safety_days).round().astype(int)
    analysis['حد إعادة الطلب'] = (recent_rate * lead_days + analysis['مخزون الأمان']).round().astype(int)
    target_days = lead_days + safety_days + review_days
    analysis['كمية الطلب المقترحة'] = (recent_rate * target_days - analysis['الكمية']).clip(lower=0).round().astype(int)
    cover = analysis['تغطية المخزون بالأيام']
    has_recent_demand = analysis[recent_column] > 0
    critical = has_recent_demand & ((analysis['الكمية'] <= 0) | (cover <= lead_days))
    high = has_recent_demand & ~critical & ((analysis['الكمية'] <= analysis['حد إعادة الطلب']) | (cover <= lead_days + safety_days))
    watch = has_recent_demand & ~critical & ~high & ((analysis['اتجاه الطلب'] == 'صاعد') & (cover <= target_days))
    analysis['أولوية الطلب'] = 'لا يحتاج'
    analysis.loc[watch, 'أولوية الطلب'] = 'مراقبة'
    analysis.loc[high, 'أولوية الطلب'] = 'عالية'
    analysis.loc[critical, 'أولوية الطلب'] = 'حرجة'
    analysis['حالة الطلب'] = 'لا يحتاج'
    reorder_mask = critical | high | watch
    analysis.loc[reorder_mask, 'حالة الطلب'] = 'إعادة طلب'

    def decision_reason(row):
        if row['أولوية الطلب'] == 'لا يحتاج':
            if row[recent_column] <= 0:
                return 'لا يوجد طلب حديث؛ راجع التصريف بدلاً من الشراء'
            return 'الرصيد يغطي مدة التوريد والأمان والمراجعة'
        cover_text = f"تغطية {row['تغطية المخزون بالأيام']:.0f} يوم" if pd.notna(row['تغطية المخزون بالأيام']) else 'لا توجد تغطية'
        purchase_text = f"آخر توريد منذ {int(row['أيام منذ آخر شراء/توريد'])} يوم" if pd.notna(row['أيام منذ آخر شراء/توريد']) else 'لا يوجد شراء/توريد مطابق للمرجع المحدد'
        return f"{cover_text}؛ الطلب {row['اتجاه الطلب']}؛ {purchase_text}"
    analysis['سبب القرار'] = analysis.apply(decision_reason, axis=1)
    clearance_mask = (analysis['الكمية'] > 0) & (analysis['آخر إخراج'].isna() | (analysis['أيام منذ آخر خروج'] >= slow_days) | (analysis['سرعة الحركة'] == 'بطيئة'))
    analysis['اقتراح التصريف'] = ''
    analysis.loc[clearance_mask, 'اقتراح التصريف'] = 'مرشح للتصريف'
    analysis['فترة التحليل'] = f'آخر {demand_window_days} يوم'
    priority_order = {'حرجة': 0, 'عالية': 1, 'مراقبة': 2, 'لا يحتاج': 3}
    analysis['ترتيب الأولوية'] = analysis['أولوية الطلب'].map(priority_order)
    return analysis.sort_values(['ترتيب الأولوية', 'كمية الطلب المقترحة'], ascending=[True, False]).drop(columns=['ترتيب الأولوية']).reset_index(drop=True)

def stock_item_key(row):
    persisted_key = str(row.get('مفتاح المخزون', '') or '').strip()
    if persisted_key:
        return persisted_key
    code = normalize_item_code(row.get('رمز المادة', ''))
    return f'CODE:{code}' if code else f"NAME:{normalize_item_name(row.get('اسم المادة', ''))}"

def ensure_unique_stock_keys(stock_df):
    if 'مفتاح المطابقة' not in stock_df.columns:
        stock_df['مفتاح المطابقة'] = stock_df['اسم المادة'].map(normalize_item_name)
    existing = stock_df.get('مفتاح المخزون')
    if existing is not None and existing.notna().all() and existing.is_unique:
        return stock_df
    base_keys = stock_df.apply(lambda row: f"CODE:{normalize_item_code(row.get('رمز المادة', ''))}" if normalize_item_code(row.get('رمز المادة', '')) else f"NAME:{normalize_item_name(row.get('اسم المادة', ''))}", axis=1)
    duplicate_number = base_keys.groupby(base_keys).cumcount()
    stock_df['مفتاح المخزون'] = [base_key if number == 0 else f'{base_key}#{number + 1}' for base_key, number in zip(base_keys, duplicate_number)]
    return stock_df

COL_CODE = "رمز المادة"
COL_NAME = "اسم المادة"
COL_QTY = "الكمية"
COL_MATCH = "مفتاح المطابقة"
COL_KEY = "مفتاح المخزون"
COL_DATE = "التاريخ"
COL_REF = "المرجع"
COL_IN = "إدخال"
COL_OUT = "إخراج"
COL_BAL = "الرصيد"
COL_USER = "المستخدم"
COL_CUSTOMER = "الزبون"
COL_NOTE = "بيان"
