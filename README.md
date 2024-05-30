# InvoiceHarbor

InvoiceHarbor extracts invoice data from AWS Invoices and Credits PDF files and stores them in a CSV file.

## Installation

Python 3.12 or higher is required.

```bash
pip install -r requirements.txt
```

### Update dependencies

```bash
pip-compile requirements.in --upgrade
```

## Usage

Set `OPENAI_API_KEY` environment variable to your OpenAI API key.

### Running the extraction

Use the `main.py` script to run the extraction.

```text
usage: main.py [-h] [--concurrency CONCURRENCY] [--max_docs MAX_DOCS] [--data_dir DATA_DIR] [--model MODEL] [--output OUTPUT] [--service SERVICE] [--kwargs KWARGS]

options:
  -h, --help            show this help message and exit
  --concurrency CONCURRENCY
                        number of concurrent requests to make
  --max_docs MAX_DOCS   maximum number of documents to process
  --data_dir DATA_DIR   folder to scan for documents
  --model MODEL         model name
  --output OUTPUT       output file name
  --service SERVICE     service to use for LLM models (openai or bedrock)
  --kwargs KWARGS       additional arguments for the model (dict)
```

```bash
# Run with 60 concurrent requests, process 200 documents, and scan ./data/05-2024 folder
python main.py --concurrency=60 --max_docs=200 --data_dir=./data/05-2024 --output=invoices-2024-05.csv

# output is written to invoices.csv
head invoices.csv
```


## License

[MIT](https://choosealicense.com/licenses/mit/)
