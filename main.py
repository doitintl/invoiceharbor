import asyncio
import argparse
import os
import textwrap
import pandas as pd
import time
from langchain.document_loaders import PyMuPDFLoader
from langchain.chains import LLMChain
from langchain.output_parsers import PydanticOutputParser
from langchain.prompts import PromptTemplate
from langchain.chat_models import ChatOpenAI
from pydantic import BaseModel, Field


# Define a new Pydantic model with field descriptions and tailored for AWS Invoice/Credit Record.
class AwsInvoiceCredit(BaseModel):
    file_name: str = Field(description="AWS Invoice PDF file name.")
    doit_payer_id: str = Field(description="Doit Payer ID. Can be extracted from the parent folder name.")
    aws_account_number: str = Field(description="AWS Account number.")
    address_company: str = Field(
        description="Address or Bill to Address company name. Use first line of the address. Usually, it is the company name.")
    address_attn: str = Field(
        description="Address or Bill to Address ATTN. Use second line of the address. Usually, it is the name of the person.")
    address_country: str = Field(
        description="Bill to address country. Use last line of the address. Usually, it is the country name. Convert short country code to a full country name.")
    document_type: str = Field(
        description="Document Type. Can be Invoice or Credit Note. Credit Note can be Credit Memo or Credit Adjustment Note.")
    billing_period: str = Field(description="Billing Period; Two dates separated by a dash; leave empty if not present")
    tax_registration_number: str = Field(default=None,
                                         description="Tax Registration Number; ABN Number; GST/HST Registration number; leave empty if not present")
    invoice_number: str = Field(description="Invoice Number from the Invoice Summary")
    invoice_date: str = Field(default=None, description="Invoice Date from the Invoice Summary")
    original_invoice_number: str = Field(default=None,
                                         description="Original Invoice Number from the Invoice Summary of Credit Memo/Note; leave empty if not present")
    original_invoice_date: str = Field(default=None,
                                       description="Original Invoice Date from the Invoice Adjustment Summary of Credit Memo/Note; leave empty if not present")
    total_amount: float = Field(
        description="Total Amount from the Invoice Summary; without currency; add minus sign if parentheses around or has a minus prefix")
    total_amount_currency: str = Field(
        description="Total Amount Currency from the Invoice Summary; use currency code instead of symbol")
    total_vat_tax_amount: float = Field(default=None,
                                        description="Total VAT/Tax Amount from the Invoice Summary; without currency; add minus sign if parentheses around or has a minus prefix")
    total_vat_tax_currency: str = Field(default=None,
                                        description="VAT/Tax Currency from the Invoice Summary; use currency code instead of symbol")
    vat_percentage: float = Field(default=None,
                                  description="VAT Percentage from the Invoice Summary Table; MUST be a number following a % sign; formatted as VAT - <number>%; GST amount at <number>%; HST Amount at <number>%; leave empty if not present or not a number between 0 and 100")
    exchange_rate: float = Field(default=None,
                                 description="Exchange Rate from the Invoice Summary Table (1 USD = ?); leave empty if not found")


# remove everything after one of the following lines (including the line itself)
def remove_footer(text):
    # remove everything after one of the following lines (including the line itself)
    lines = [
        "* May include estimated US sales tax, VAT, ST, GST and CT.",
        "Amazon Web Services EMEA SARL",
        "Amazon Web Services Australia Pty Ltd",
        "AMAZON WEB SERVICES EMEA SARL",
        "Amazon Web Services Canada, Inc.",
        "Amazon Web Services EMEA SARL, Luxembourg, Zweigniederlassung Zürich",
    ]
    for line in lines:
        if line in text:
            return text.split(line)[0]
    return text


# scan all documents in the folder (recursively)
def scan_folder(folder):
    documents = []
    for root, dirs, files in os.walk(folder):
        for file in files:
            if file.endswith(".pdf"):
                loader = PyMuPDFLoader(os.path.join(root, file))
                data = loader.load()
                invoice = remove_footer(data[0].page_content)
                # get parent folder name
                parent_folder = os.path.basename(os.path.dirname(os.path.join(root, file)))
                # extract doit payer id from the parent folder name
                payer_id = parent_folder.split("_")[1]
                # add file name to the invoice
                invoice = f"File name: {file}\nDoiT payer id: {payer_id}\n" + invoice
                documents.append(invoice)
    return documents


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
                    Extract data from the AWS Invoice or Credit document into a flat JSON object.
                    {format_instructions}
                    {request}
                    <document>
                    {invoice}
                    <document>
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
                Return the extracted fields in the valid JSON format: only JSON objects and arrays are allowed without any comments or other text. 
                Keep it as simple as possible and ensure the JSON is valid. 
                Skip the fields that are not present in the invoice.
                Be careful with the currency symbols, which are not always in the invoice.
                Try to extract the fields even if the invoice format differs and the fields are not in the same order. 
                My job depends on it! And I will be very grateful to you! Will pay you an extra 1000$ if you do it without errors!
                """
            )
            chain = LLMChain(llm=model, prompt=prompt)
            retries = 2  # number of retries
            while retries > 0:
                try:
                    output = await chain.arun(request=parsing_request, invoice=document)
                    # remove everything before the first { and after the last }
                    output = output[output.find("{"):output.rfind("}") + 1]
                    parsed = parser.parse(output)
                    return parsed
                except Exception as e:
                    retries -= 1
                    if retries == 0:
                        raise Exception(f"Error processing document {file_name}: {e}")
        except Exception as e:
            raise Exception(f"Error processing document {file_name}: {e}")


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("concurrency", type=int, help="number of concurrent requests to make", default=50)
    parser.add_argument("max_docs", type=int, help="maximum number of documents to process", default=0)
    parser.add_argument("data_dir", type=str, help="folder to scan for documents", default="./data")
    args = parser.parse_args()

    # Instantiate the semaphore to limit the number of concurrent requests.
    # Approximate number of tokens per request is 1000-1500, so 50 requests will be 75k tokens
    # a single request takes 10 seconds, so 30 concurrent requests can lead to 180 requests per minute
    # 180 * 1500 = 270k tokens per minute (TPM) should be within the 600k TPM limit
    sem = asyncio.Semaphore(args.concurrency)

    # Instantiate the model.
    llm = ChatOpenAI(
        model="gpt-4-1106-preview",
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        temperature=0.0,
        max_tokens=4096,
    )

    # measure time
    start = time.time()

    # Scan the folder for documents
    all_documents = scan_folder(args.data_dir)
    print(f"Found {len(all_documents)} documents")
    end_scan = time.time()
    print(f"Time elapsed: {end_scan - start} seconds")

    # Loop over the max documents
    max_docs = len(all_documents) if args.max_docs == 0 else args.max_docs
    tasks = []
    for i, doc in enumerate(all_documents[:max_docs]):
        # Extract data from the document (async)
        tasks.append(extract_data(llm, doc, sem))

    # Create a CSV file and write the results as they become available
    with open('invoices.csv', 'w') as f:
        for future in asyncio.as_completed(tasks):
            result = await future
            if isinstance(result, Exception):
                print(result)
            else:
                # Convert the result to a DataFrame and append it to the CSV file
                try:
                    record = result.model_dump()
                    df_temp = pd.DataFrame.from_dict(record, orient='index').transpose()
                    df_temp.to_csv(f, header=f.tell() == 0, index=False)
                    print(f"Added record for: {record['file_name']}")
                except Exception as e:
                    print(f"Error saving record: {e}")

    # measure time
    end = time.time()
    print(f"Time elapsed: {end - end_scan} seconds")


asyncio.run(main())
