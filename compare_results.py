import argparse
import pandas as pd
import os


def compare_values(val1, val2):
    # Check for NaN equality or one is NaN and the other is 0 or 0.0
    if (pd.isna(val1) and val2 in [0, 0.0]) or (pd.isna(val2) and val1 in [0, 0.0]):
        return True
    elif pd.isna(val1) and pd.isna(val2):
        return True
    # Handle string-specific comparisons (trim and case-insensitive)
    if isinstance(val1, str) and isinstance(val2, str):
        return val1.strip().lower() == val2.strip().lower()
    # Handle floating-point numbers with a tolerance
    elif isinstance(val1, float) and isinstance(val2, float):
        return abs(val1 - val2) < 0.0001
    # Direct comparison for other types
    else:
        return val1 == val2


def compare_csv_files(test_path, experiment_path, output_path=None, prefix="invoices-", skip_columns_list=None):
    # Load CSV files into DataFrames
    if skip_columns_list is None:
        skip_columns_list = []
    test = pd.read_csv(test_path)
    experiment = pd.read_csv(experiment_path)

    # Record the original column order from the test DataFrame
    original_column_order = test.columns.tolist()

    # Identify common columns between the two DataFrames
    common_columns = list(set(test.columns).intersection(set(experiment.columns)))
    test = test[common_columns]
    experiment = experiment[common_columns]

    # Check if "file_name" column exists in both DataFrames
    if "file_name" not in test.columns or "file_name" not in experiment.columns:
        raise ValueError("The 'file_name' column must be present in both CSV files.")

    # Sort both DataFrames by the "file_name" column
    test = test.sort_values(by="file_name").reset_index(drop=True)
    experiment = experiment.sort_values(by="file_name").reset_index(drop=True)

    similar_rows = 0
    different_rows = 0
    differences = []  # This will store pandas Series directly

    # Compare rows between test and experiment DataFrames
    for i in range(len(test)):
        row_equal = True
        for col in test.columns:
            # Skip comparison for columns in skip_columns_list
            if col in skip_columns_list:
                continue

            test_value = test.iloc[i][col]
            experiment_value = experiment.iloc[i][col]

            if not compare_values(test_value, experiment_value):
                row_equal = False
                # Debugging aid: Uncomment the following line to see which values are different
                # print(f"Difference in row {i}, column {col}: {test_value} vs {experiment_value}")
                break

        if not row_equal:
            different_rows += 1
            # Create a copy of the row from 'test' and add a new column
            test_row = test.iloc[i].copy()
            # extract the file name from the path and add it as a new column without the prefix and .csv
            name = os.path.basename(test_path)
            name = name.replace(prefix, '')
            name = name.replace('.csv', '')
            test_row = pd.concat([pd.Series([name], index=['model_name']), test_row])
            # Create a copy of the row from 'experiment' and add a new column
            experiment_row = experiment.iloc[i].copy()
            # extract the file name from the path and add it as a new column without the prefix and .csv
            name = os.path.basename(experiment_path)
            name = name.replace(prefix, '')
            name = name.replace('.csv', '')
            experiment_row = pd.concat([pd.Series([name], index=['model_name']), experiment_row])

            # Append differing rows as Series directly
            differences.append(test_row)
            differences.append(experiment_row)
        else:
            similar_rows += 1

    print(f"Similar rows: {similar_rows}, Different rows: {different_rows}")

    # If there are differences and an output path is provided, write them to a CSV file
    if differences and output_path:
        differences_df = pd.DataFrame(differences)
        updated_column_order = ['model_name'] + [col for col in original_column_order if col in differences_df.columns]
        differences_df = differences_df[updated_column_order]
        differences_df.to_csv(output_path, index=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compare two CSV files and optionally output differences to a new file.")
    parser.add_argument("--test_path", type=str, help="Path to the test data CSV file")
    parser.add_argument("--experiment_path", type=str, help="Path to the experiment data CSV file")
    parser.add_argument("--output_path", type=str, help="Path to the output CSV file for differences", required=False)  # Ensure this matches the function parameter
    parser.add_argument("--prefix", type=str, help="Prefix to remove from the file name in the output file", required=False)
    parser.add_argument("--skip_columns", type=str, help="Comma-separated list of columns to skip from comparison",
                        default="")
    args = parser.parse_args()
    compare_csv_files(args.test_path, args.experiment_path, args.output_path, args.prefix, args.skip_columns.split(","))
