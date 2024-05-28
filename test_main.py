import json
import pytest
import asyncio
from unittest.mock import patch, MagicMock
from main import AwsInvoiceCredit, remove_footer, scan_folder, get_sorted_column_values, extract_data


def test_aws_invoice_credit_model():
    data = {
        "file_name": "invoice.pdf",
        "doit_payer_id": "123",
        "document_type": "Invoice",
        "aws_account_number": "456",
        "address_company": "AWS Inc.",
        "address_attn": "John Doe",
        "address_country": "United States",
        "tax_registration_number": "789",
        "billing_period": "January 1, 2022 - January 31, 2022",
        "invoice_number": "101112",
        "invoice_date": "January 31, 2022",
        "original_invoice_number": "131415",
        "original_invoice_date": "January 1, 2022",
        "total_amount": 100.0,
        "total_amount_currency": "USD",
        "total_vat_tax_amount": 10.0,
        "total_vat_tax_currency": "USD",
        "net_charges_usd": 90.0,
        "net_charges_non_usd": 90.0,
        "net_charges_currency": "USD",
        "vat_percentage": 10.0,
        "exchange_rate": 1.0,
        "amazon_company_name": "Amazon Web Services, Inc.",
        "amazon_company_branch": "EMEA SARL"
    }
    model = AwsInvoiceCredit(**data)
    assert model.dict() == data


def test_remove_footer():
    text = "This is a test text. * May include estimated US sales tax, VAT, ST, GST and CT."
    assert remove_footer(text) == "This is a test text. "


@patch('os.walk')
@patch('main.PyMuPDFLoader')
def test_scan_folder(mock_loader, mock_walk):
    # Mock the return value of PyMuPDFLoader.load method
    mock_loader.return_value.load.return_value = [MagicMock(page_content='test content')]

    mock_walk.return_value = [
        ('root', 'dirs', ['data/1234_doit-payer-1/file1.pdf', 'data/1234_doit-payer-1/file2.pdf'])
    ]
    assert len(scan_folder('folder', max_docs=1)) == 1


def test_get_sorted_column_values():
    with patch('builtins.open', new_callable=MagicMock) as mock_open:
        mock_open.return_value.__enter__.return_value.__iter__.return_value = iter(['header', 'value'])
        assert get_sorted_column_values('file.csv', 0) == ['value']


@pytest.mark.asyncio
@patch('main.LLMChain')
async def test_extract_data(mock_chain):
    mock_chain.return_value.ainvoke.return_value = asyncio.Future()
    mock_chain.return_value.ainvoke.return_value.set_result({
        "text": json.dumps({
            "file_name": "invoice.pdf",
            "doit_payer_id": "123",
            "document_type": "Invoice",
            "aws_account_number": "456",
            "address_company": "AWS Inc.",
            "address_attn": "John Doe",
            "address_country": "United States",
            "tax_registration_number": "789",
            "billing_period": "January 1, 2022 - January 31, 2022",
            "invoice_number": "101112",
            "invoice_date": "January 31, 2022",
            "original_invoice_number": "131415",
            "original_invoice_date": "January 1, 2022",
            "total_amount": 100.0,
            "total_amount_currency": "USD",
            "total_vat_tax_amount": 10.0,
            "total_vat_tax_currency": "USD",
            "net_charges_usd": 90.0,
            "net_charges_non_usd": 90.0,
            "net_charges_currency": "USD",
            "vat_percentage": 10.0,
            "exchange_rate": 1.0,
            "amazon_company_name": "Amazon Web Services, Inc.",
            "amazon_company_branch": "EMEA SARL"
        })
    })
    document = "File name: file.pdf\nDoiT payer id: 123\nInvoice"
    sem = asyncio.Semaphore(1)
    model = MagicMock()
    result = await extract_data(model, document, sem)
    assert isinstance(result, AwsInvoiceCredit)