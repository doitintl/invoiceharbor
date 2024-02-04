import asyncio
import argparse
import csv
import os
import textwrap
import time
from langchain.document_loaders import PyMuPDFLoader
from langchain.chains import LLMChain
from langchain.output_parsers import PydanticOutputParser
from langchain.prompts import PromptTemplate
from langchain.chat_models import ChatOpenAI
from pydantic import BaseModel, Field
from typing import Optional


# Define a new Pydantic model with field descriptions and tailored for AWS Invoice/Credit Record.
class AwsInvoiceCredit(BaseModel):
    file_name: str = Field(description="AWS Invoice PDF file name")
    doit_payer_id: str = Field(description="Doit Payer ID")
    document_type: str = Field(
        description="Document Type: can be 'Invoice' or 'Credit Note' only. Credit Note can be Credit Memo or Credit Adjustment Note.")
    aws_account_number: str = Field(description="AWS Account number")
    address_company: str = Field(
        description="Address or Bill to Address company name. Use first line of the address. Usually, it is the company name.")
    address_attn: str = Field(
        description="Address or Bill to Address ATTN (skip the ATTN prefix). Use second line of the address. Usually, it is the name of the person.")
    address_country: str = Field(
        description="Bill to address country. Use last line of the address. Usually, it is the country name. Convert country code to a full country name.")
    tax_registration_number: Optional[str] = Field(default=None,
                                                   description="Tax Registration Number or ABN Number or GST Number or GST/HST Registration number or  Issued To; usually the next number after AWS Account Number")
    billing_period: str = Field(description="Billing Period; Two dates separated by a dash")
    invoice_number: str = Field(description="Invoice Number from the Invoice Summary")
    invoice_date: str = Field(description="Invoice Date from the Invoice Summary")
    original_invoice_number: Optional[str] = Field(default=None,
                                                   description="Original Invoice Number from the Invoice Summary of Credit Memo/Note; leave empty if not present")
    original_invoice_date: Optional[str] = Field(default=None,
                                                 description="Original Invoice Date from the Invoice Adjustment Summary of Credit Memo/Note; leave empty if not present")
    total_amount: float = Field(
        description="Total Amount from the Invoice Summary; without currency; add minus sign if parentheses around or has a minus prefix")
    total_amount_currency: str = Field(
        description="Total Amount Currency from the Invoice Summary; use currency code instead of symbol")
    total_vat_tax_amount: Optional[float] = Field(default=None,
                                                  description="(Total) VAT/Tax Amount from the (Invoice) Summary; without currency; add minus sign if parentheses around or has a minus prefix")
    total_vat_tax_currency: Optional[str] = Field(default=None,
                                                  description="VAT/Tax Currency from the (Invoice) Summary; use currency code instead of symbol")
    net_charges_usd: Optional[float] = Field(default=None,
                                             description="(Net) Charges (USD) (After Credits/Discounts, excl. Tax) from the (Invoice) Summary; without currency; add minus sign if parentheses around or has a minus prefix")
    net_charges_non_usd: Optional[float] = Field(default=None,
                                                 description="Net Charges (non-USD) (After Credits/Discounts, excl. Tax) in local currency from the Invoice Summary; without currency; add minus sign if parentheses around or has a minus prefix")
    net_charges_currency: Optional[str] = Field(default=None,
                                                description="Net Charges (non-USD) local currency; use currency code instead of symbol")
    vat_percentage: Optional[float] = Field(default=None,
                                            description="Extract VAT percent (without % sign) from one of these fields: VAT - <number>% or VAT in <percent> or GST amount at <percent> or HST Amount at <percent>")
    exchange_rate: Optional[float] = Field(default=None,
                                           description="Exchange Rate from the (1 USD = <rate> currency) formula")
    amazon_company_name: str = Field(
        description="Amazon Web Services company name. Usually, it is Amazon Web Services, Inc. but can be different for different countries")
    amazon_company_branch: Optional[str] = Field(default=None,
                                                 description="Amazon Web Services company branch. Usually, it is after Amazon Web Services EMEA SARL but can be different for different countries")


# remove everything after one of the following lines (including the line itself)
def remove_footer(text):
    # remove everything after one of the following lines (including the line itself)
    lines = [
        "* May include estimated US sales tax, VAT, ST, GST and CT.",
    ]
    for line in lines:
        if line in text:
            return text.split(line)[0]
    return text


# scan all documents in the folder (recursively)
def scan_folder(folder, max_docs=0, processed_files=None):
    if processed_files is None:
        processed_files = []
    documents = []
    doc_count = 0
    for root, dirs, files in os.walk(folder):
        for file in files:
            if file.endswith(".pdf") and file not in processed_files:
                loader = PyMuPDFLoader(os.path.join(str(root), str(file)))
                data = loader.load()
                invoice = remove_footer(data[0].page_content)
                # get parent folder name
                parent_folder = os.path.basename(os.path.dirname(os.path.join(root, file)))
                # extract doit payer id from the parent folder name
                payer_id = parent_folder.split("_")[1]
                # add file name to the invoice
                invoice = f"File name: {file}\nDoiT payer id: {payer_id}\n" + invoice
                documents.append(invoice)
                doc_count += 1
                if max_docs != 0 and doc_count >= max_docs:
                    return documents
    return documents


# get sorted column values from a CSV file
def get_sorted_column_values(file_name, column_index):
    try:
        with open(file_name, 'r', newline='') as csvfile:
            reader = csv.reader(csvfile)
            next(reader)  # Skip the header row
            column_values = [row[column_index] for row in reader if len(row) > column_index]
        column_values.sort()
        return column_values
    except FileNotFoundError:
        print(f"The file {file_name} was not found.")
        return []
    except Exception as e:
        print(f"An error occurred: {e}")
        return []


# extract data from the document
async def extract_data(model, document, sem):
    async with sem:
        # Update the prompt to match the new query and desired format.
        try:
            # Instantiate the parser with the new model.
            parser = PydanticOutputParser(pydantic_object=AwsInvoiceCredit)
            # Get the file name from the first line of the document
            file_name = document.split("\n")[0].split(":")[1].strip()
            # Update the prompt to match the new query and desired format.
            prompt = PromptTemplate(
                template=textwrap.dedent(
                    """
                    The following document is a plain text extracted from AWS Invoice or Credit Note PDF file.
                    
                    <document>
                    {invoice}
                    <document>
                    
                    Act as an accountant and extract data from the above document into a flat JSON object.
                    {format_instructions}
                    {request}
                    
                    JSON:
                    """
                ),
                input_variables=["request", "invoice"],
                partial_variables={
                    "format_instructions": parser.get_format_instructions(),
                },
            )
            # Generate the input using the updated prompt.
            parsing_request = textwrap.dedent(
                """
                Tips:
                - Convert all dates to "Month name Day, Year" format with no leading zeros
                - Format all dates according to "Month name Day, Year" format with no leading zeros
                - Convert alpha-2 country code to a full country name
                - Branch name should not contain a full company name
                - Be careful with charges and amount signs, they are usually negative for credits
                - Extract exchange rate (X) from (1 USD = X currency) pattern
                """
            )
            chain = LLMChain(llm=model, prompt=prompt)
            output = await chain.arun(request=parsing_request, invoice=document)
            # remove everything before the first { and after the last }
            output = output[output.find("{"):output.rfind("}") + 1]
            parsed = parser.parse(output)
            return parsed
        except Exception as e:
            # returning and not raising the exception to continue processing other documents
            return Exception(f"Error processing document {file_name}: {e}")


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--concurrency", type=int, help="number of concurrent requests to make", default=50,
                        required=False)
    parser.add_argument("--max_docs", type=int, help="maximum number of documents to process", default=0,
                        required=False)
    parser.add_argument("--data_dir", type=str, help="folder to scan for documents", default="./data")
    parser.add_argument("--model", type=str, help="model name", default="gpt-4-1106-preview", required=False)
    parser.add_argument("--output", type=str, help="output file name", default="invoices.csv", required=False)
    args = parser.parse_args()

    # Instantiate the semaphore to limit the number of concurrent requests.
    # Approximate number of tokens per request is 1000-1500, so 50 requests will be 75k tokens
    # a single request takes 10 seconds, so 30 concurrent requests can lead to 180 requests per minute
    # 180 * 1500 = 270k tokens per minute (TPM) should be within the 600k TPM limit
    sem = asyncio.Semaphore(args.concurrency)

    # Instantiate the model.
    llm = ChatOpenAI(
        model=args.model,
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        temperature=0.0,
        max_tokens=4096,
        model_kwargs={"top_p": 0.0}
    )

    # measure time
    start = time.time()

    processed_files = []
    if os.path.isfile(args.output):
        processed_files = get_sorted_column_values(args.output, 0)

    # Scan the folder for documents up to the max documents if specified
    all_documents = scan_folder(args.data_dir, args.max_docs, processed_files)
    print(f"Found {len(all_documents)} documents")
    end_scan = time.time()
    print(f"Time elapsed: {end_scan - start} seconds")

    # Check if the file exists
    if os.path.isfile(args.output):
        # If the file exists, read the header
        with open(args.output, 'r', newline='') as csvfile:
            reader = csv.reader(csvfile)
            header = next(reader)  # Read the header row
    else:
        # If the file does not exist, create a new header based on the fields of the AwsInvoiceCredit model
        header = [field for field in AwsInvoiceCredit.__annotations__.keys()]

    # Loop over the all scanned documents
    tasks = []
    for i, doc in enumerate(all_documents):
        # Extract data from the document (async)
        tasks.append(extract_data(llm, doc, sem))

    # Create a CSV file and write the results as they become available
    with open(args.output, 'a', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=header)
        # If the file is empty, write the header
        if f.tell() == 0:
            writer.writeheader()
        # Write the results as they become available
        for future in asyncio.as_completed(tasks):
            result = await future
            if isinstance(result, Exception):
                print(result)
            else:
                # Convert the result to a DataFrame and append it to the CSV file
                try:
                    record = result.model_dump()
                    # Fill missing keys with None or you can use an empty string ''
                    row = {key: record.get(key, None) for key in header}
                    writer.writerow(row)
                    print(f"Added record for: {record['file_name']}")
                except Exception as e:
                    print(f"Error saving record: {e}")

    # measure time
    end = time.time()
    print(f"Time elapsed: {end - end_scan} seconds")


asyncio.run(main())
