def dataframe_to_json(dataframes):
    """
    Convert pandas DataFrames to JSON-like dict
    """
    result = {}
    for key, df in dataframes.items():
        result[key] = df.to_dict(orient="records")
    return result
