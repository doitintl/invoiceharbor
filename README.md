# InvoiceHarbor

InvoiceHarbor extracts invoice data from AWS Invoices and Credits PDF files and stores them in a CSV file.

## Installation

Python 3.6 or higher is required.

```bash
install -r requirements.txt
```

## Usage

Set `OPENAI_API_KEY` environment variable to your OpenAI API key.

### Running the extraction

Use the `main.py` script to run the extraction.

```text
usage: main.py [-h] concurrency max_docs data_dir

positional arguments:
  concurrency  number of concurrent requests to make
  max_docs     maximum number of documents to process
  data_dir     folder to scan for documents

options:
  -h, --help   show this help message and exit
```

```bash
# Run with 50 concurrent requests, process 100 documents, and scan ./data/12-2023 folder
python main.py 50 100 ./data/12-2023

# output is written to invoices.csv
head invoices.csv
```

### Running the experiment

Run the `playground_openai.py` Jupiter notebook.

To see progress, run `watch -n 1 wc -l invoices.csv`.

## License

[MIT](https://choosealicense.com/licenses/mit/)
