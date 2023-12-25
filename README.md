# InvoiceHarbor

InvoiceHarbor extracts invoice data from AWS Invoices and Credits PDF files and stores them in a CSV file.

## Installation

Python 3.6 or higher is required.

```bash
install -r requirements.txt
```

## Usage

Set `OPENAI_API_KEY` environment variable to your OpenAI API key.

Run the `playground_openai.py` Jupiter notebook.

To see progress, run `watch -n 1 wc -l invoices.csv`.

## License

[MIT](https://choosealicense.com/licenses/mit/)
