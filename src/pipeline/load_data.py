import pandas as pd

def load_excel(path):
    """
    Load Excel file and convert all timestamps to strings
    to avoid JSON serialization issues.
    """
    xls = pd.ExcelFile(path)
    data = {}

    for sheet in xls.sheet_names:
        df = xls.parse(sheet)

        # 将所有 Timestamp 转换成 string
        for col in df.columns:
            if pd.api.types.is_datetime64_any_dtype(df[col]):
                df[col] = df[col].astype(str)

        data[sheet] = df

    return data
