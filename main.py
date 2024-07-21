import asyncio
import argparse
import csv
import json
import os
import textwrap
import time
from langchain_community.document_loaders import PyMuPDFLoader
from langchain.output_parsers import PydanticOutputParser
from langchain.prompts import PromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_openai import ChatOpenAI
from langchain_community.chat_models import BedrockChat
from pydantic import BaseModel, Field
from typing import Optional


# Define a new Pydantic model with field descriptions and tailored for AWS Invoice/Credit Record.
class AwsInvoiceCredit(BaseModel):
    file_name: str = Field(description="Name of the AWS invoice PDF file.")
    doit_payer_id: str = Field(description="Doit Payer ID: Unique identifier for the payer in the DoiT system.")
    document_type: str = Field(
        description="Determine the document type based on content analysis. Classify as 'Invoice' if it primarily details charges, or 'Credit Note' if it contains references to 'Credit Memo', 'Credit Adjustment Note', 'Tax Invoice Adjustment', or similar terms. Additionally, consider the net total amount; classify as 'Credit Note' only if the net charges after credits/discounts are negative.")
    ri_invoice: Optional[bool] = Field(default=None, description="Indicates if the invoice is for a Reserved Instance (RI), identifiable by '(one time fee)' mention. True for RI invoices, None otherwise or if not applicable.")
    aws_account_number: str = Field(description="The AWS account number associated with the invoice.")
    address_company: str = Field(
        description="The company name as it appears on the invoice's billing address. Typically the first line of the address before ATTN line.")
    address_attn:  Optional[str] = Field(
        description="The attention line of the billing address, excluding the 'ATTN' prefix. Typically the second line of the address. Usually, it is the name of the person.")
    address_country: str = Field(
        description="The country name in the billing address. Typically the last line of the address. Convert alpha-2 country codes to full country names. For example, US to United States.")
    tax_registration_number: Optional[str] = Field(default=None,
                                                   description=" The tax registration number (e.g., ABN, GST Number, GST/HST Registration, Issued To) as listed on the invoice, excluding AWS's tax number. Typically the next number after AWS Account Number. Ignore if found after the billing period.")
    invoice_number: str = Field(description="The invoice number as provided in the invoice summary.")
    invoice_date: str = Field(description="The date the invoice was issued as provided in the invoice summary.")
    allocation_number: Optional[str] = Field(default=None, description="The allocation number from the invoice summary, if present.")
    original_invoice_number: Optional[str] = Field(default=None,
                                                   description="For credit notes, the original invoice number related to the adjustment. For regular invoices it can be a replacement for invoice (typically found after billing period). Leave blank if not applicable.")
    original_invoice_date: Optional[str] = Field(default=None,
                                                 description="For credit notes, the date of the original invoice being adjusted. Leave blank if not applicable.")
    total_amount: float = Field(
        description="The total amount charged or credited on the invoice, without currency symbols. Reflects the net result of all charges and credits on the invoice. This should be 0 if charges are fully offset by credits, rather than summing up the individual credit amounts. Ensure to use negative values for credits.")
    total_amount_currency: str = Field(
        description="The currency code for the total amount, as listed on the invoice.")
    total_vat_tax_amount: Optional[float] = Field(default=None,
                                                  description="The total VAT or tax amount, extracted from the section immediately following 'TOTAL VAT' or 'TOTAL Tax', without currency symbols. If the document shows a net zero VAT or tax charge, this field should be set to 0. Use negative values for credits. If exists, always before the billing period.")
    total_vat_tax_currency: Optional[str] = Field(default=None,
                                                  description="The currency code for the total VAT or tax amount, determined from the section immediately following 'TOTAL VAT' or 'TOTAL Tax'.")
    billing_period: str = Field(
        description="The billing period covered by the invoice. Typically formatted as two dates separated by a dash. Please, format both date according to the 'Month name Day, Year' format with no leading zeros fix if needed (ex. January 1, 2022 - January 31, 2022)")
    net_charges_usd: Optional[float] = Field(default=None,
                                             description="Net charges in USD after credits/discounts, excluding tax, without currency symbol. Use negative values for credits.")
    net_charges_non_usd: Optional[float] = Field(default=None,
                                                 description="Net charges in non-USD currency after credits/discounts, excluding tax, without currency symbol. Use negative values for credits.")
    net_charges_currency: Optional[str] = Field(default=None,
                                                description="The currency code (replace symbol) for net charges in non-USD currency.")
    vat_percentage: Optional[float] = Field(default=None,
                                            description="The VAT rate applied, extracted (from  VAT - <number>% or VAT in % or GST amount at % or HST Amount at % and similar) without the '%' sign from the invoice.")
    exchange_rate: Optional[float] = Field(default=None,
                                           description="The exchange rate applied, formatted as per the pattern '1 USD = X currency'.")
    amazon_company_name: str = Field(
        description="The Amazon Web Services company name as listed on the invoice, which may vary by country.")
    amazon_company_branch: Optional[str] = Field(default=None,
                                                 description="The specific branch of Amazon Web Services, if mentioned, excluding full company name and address details. Typically after the 'Amazon Web Services EMEA SARL' but can be different for different countries.")


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
                # log progress every 100 documents
                if doc_count % 100 == 0:
                    print(f"Parsed {doc_count} documents")
                # break if max_docs is reached
                if max_docs != 0 and doc_count >= max_docs:
                    return documents
    return documents


# get sorted column values from a CSV file
def get_sorted_column_values(file_name, column_index):
    with open(file_name, 'r', newline='') as csvfile:
        reader = csv.reader(csvfile)
        next(reader)  # Skip the header row
        column_values = [row[column_index] for row in reader if len(row) > column_index]
    column_values.sort()
    return column_values


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
                    Act as an accountant and extract data from the following document into a flat JSON object. The output should be formatted as a JSON instance that conforms to the provided JSON schema.
                    
                    {instructions}
                    
                    {format_instructions}
                    
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
            parsing_instructions = textwrap.dedent(
                """
                **Important Instructions:**
                1. Classify the document as 'Invoice' if it primarily details charges. Classify as 'Credit Note' if it contains references to 'Credit Memo', 'Credit Adjustment Note', 'Tax Invoice Adjustment', or similar terms. Additionally, consider the net total amount; classify as 'Credit Note' only if the net charges after credits/discounts are negative.
                2. Implement a validation step to accurately determine the document type ('Invoice' or 'Credit Note') based on the presence of specific keywords and the net total amount. If the document lacks explicit credit-related terms but has a net zero or positive amount, classify it as 'Invoice'.
                3. The total amount should reflect the net outcome of all charges and credits. Record as 0 if charges are fully offset by credits, rather than summing up the individual credit amounts. Use negative values for credits.
                4. Ensure that both the total amount and the total VAT amount are negative for credits to accurately reflect credit transactions.
                5. Net charges should be negative for credits, indicating a refund or credit situation.
                6. Extract the `total_vat_tax_amount` specifically from the section labeled "TOTAL VAT" or "TOTAL Tax". This amount should be taken from the line immediately following this label, formatted as "{currency} {number}".
                7. The total VAT or tax amount should accurately reflect the net VAT or tax charges after applying any credits. Record as 0 if the net VAT or tax charge is zero.
                8. Correct negative zero values (-0.0) to positive zero (0.0) for fields like `total_amount`, `total_vat_tax_amount`, `net_charges_usd`, and `net_charges_non_usd` to ensure data accuracy and avoid confusion.
                9. Convert all dates to the "Month name Day, Year" format with no leading zeros to maintain consistency across documents.
                10. Ensure all dates are formatted according to the "Month name Day, Year" format with no leading zeros for uniformity.
                11. Convert all instances of alpha-2 country codes to their full country name equivalents to enhance readability and clarity.
                12. The branch name should exclude the full company name and should not resemble a full address, to maintain focus on relevant details.
                13. Monitor charges and amount signs carefully; they are typically negative for credits, reflecting the nature of the transaction.
                14. Extract the exchange rate from the pattern "1 USD = X currency" to facilitate accurate financial calculations.
                15. Format all numbers without commas (e.g., use 2200.58 instead of 2,200.58) for consistency and to avoid parsing errors.
                16. The billing address company cannot be the AWS company name. Ensure that the billing address company is the first line of the address before the ATTN line.
                17. Use city names to figure out the billing address country (not city), if the country name is not provided or cannot be determined.
                18. When net charges in non-USD currency are not found in the document, try to extract it from the total invoice amount in non-USD currency, if available.
                """
            )
            # Create a runnable chain
            chain = (
                    {"instructions": RunnablePassthrough(), "invoice": RunnablePassthrough()}
                    | prompt
                    | model
                    | parser
            )

            # Invoke the chain
            parsed = await chain.ainvoke({"instructions": parsing_instructions, "invoice": document})
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
    parser.add_argument("--model", type=str, help="model name", default="gpt-4o", required=False)
    parser.add_argument("--output", type=str, help="output file name", default="invoices.csv", required=False)
    parser.add_argument("--service", type=str, help="service to use for LLM models (openai or bedrock)",
                        default="openai", required=False)
    # get kwargs from the command line
    parser.add_argument('--kwargs', type=str, help="additional arguments for the model (dict)", required=False)

    args = parser.parse_args()
    kwargs = json.loads(args.kwargs) if args.kwargs else {}

    # Instantiate the semaphore to limit the number of concurrent requests.
    # Approximate number of tokens per request is 1000-1500, so 50 requests will be 75k tokens
    # a single request takes 10 seconds, so 30 concurrent requests can lead to 180 requests per minute
    # 180 * 1500 = 270k tokens per minute (TPM) should be within the 600k TPM limit
    sem = asyncio.Semaphore(args.concurrency)

    # Instantiate the model.
    if args.service == "openai":
        llm = ChatOpenAI(
            model=args.model,
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            temperature=kwargs.get("temperature", 0.0),  # default temperature is 0.0
            max_tokens=kwargs.get("max_tokens", 4096),  # default max tokens is 4096
            top_p=kwargs.get("top_p", 0.0),  # default top p is 0.0
        )
    elif args.service == "bedrock":
        llm = BedrockChat(
            credentials_profile_name=os.getenv("AWS_PROFILE"),
            model_id=args.model,
            model_kwargs=kwargs
        )
    else:
        raise ValueError("Invalid service. Choose either 'openai' or 'bedrock'.")

    # measure time
    start = time.time()

    processed_files = []
    if os.path.isfile(args.output):
        processed_files = get_sorted_column_values(args.output, 0)
        print(f"Found {len(processed_files)} processed documents")

    # Scan the folder for documents up to the max documents if specified
    all_documents = scan_folder(args.data_dir, args.max_docs, processed_files)
    print(f"Found {len(all_documents)} new documents")
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

if __name__ == "__main__":
    asyncio.run(main())
