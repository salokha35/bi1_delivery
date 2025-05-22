import aiohttp
from typing import Dict, Any
import json
import logging
import time
from datetime import datetime

# Configure logging
logger = logging.getLogger(__name__)

API_BASE_URL = "https://bi1.wyzo.shop/api/v1/admin"
ORDER_BASE_URL = "https://bi1.wyzo.shop/api/v1/admin/sales/orders"
OTP_BASE_URL = "https://bi1.wyzo.shop/api"
ROBOT_X_AUTH_TOKEN = "1a96e5abd3be6214aff4611e3b34e28ef239199e"

async def log_request(method: str, url: str, headers: Dict = None, data: Dict = None) -> None:
    """Log API request details."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    logger.info(f"\n{'='*50}\n📤 OUTGOING REQUEST [{timestamp}]")
    logger.info(f"➡️ {method} {url}")
    
    if headers:
        sanitized_headers = headers.copy()
        if 'Authorization' in sanitized_headers:
            sanitized_headers['Authorization'] = sanitized_headers['Authorization'][:20] + '...'
        logger.info("📋 Headers:")
        for key, value in sanitized_headers.items():
            logger.info(f"   {key}: {value}")
    
    if data:
        sanitized_data = data.copy() if isinstance(data, dict) else {"data": str(data)}
        if 'password' in sanitized_data:
            sanitized_data['password'] = '********'
        logger.info("📦 Body:")
        logger.info(f"   {json.dumps(sanitized_data, indent=2)}")

async def log_response(status: int, body: Any, response_time: float, headers: Dict = None) -> None:
    """Log API response details."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    logger.info(f"\n📥 INCOMING RESPONSE [{timestamp}]")
    logger.info(f"⬅️ Status: {status} (took {response_time:.2f}s)")
    
    if headers:
        logger.info("📋 Headers:")
        for key, value in headers.items():
            logger.info(f"   {key}: {value}")
    
    logger.info("📦 Body:")
    if isinstance(body, (dict, list)):
        sanitized_body = json.dumps(body, indent=2)
        if len(sanitized_body) > 1000:
            sanitized_body = sanitized_body[:1000] + "... [truncated]"
        logger.info(f"   {sanitized_body}")
    else:
        logger.info(f"   {str(body)[:1000]}")
    logger.info("="*50)

class APIError(Exception):
    def __init__(self, status: int, message: str):
        self.status = status
        self.message = message
        super().__init__(f"API Error {status}: {message}")

async def authenticate_user(email: str, password: str) -> Dict[str, Any]:
    """Authenticate user and return access token."""
    url = f"{API_BASE_URL}/login"
    start_time = time.time()
    
    # Create form data
    form_data = aiohttp.FormData()
    form_data.add_field("email", email)
    form_data.add_field("password", password)
    form_data.add_field("device_name", "pc")

    # Log request
    await log_request(
        method="POST",
        url=url,
        headers={"Accept": "application/json"},
        data={"email": email, "password": "********", "device_name": "pc"}
    )

    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, data=form_data, headers={"Accept": "application/json"}) as resp:
                response_time = time.time() - start_time
                response_body = await resp.text()
                
                try:
                    response_json = json.loads(response_body)
                except json.JSONDecodeError:
                    response_json = response_body

                # Log response
                await log_response(
                    status=resp.status,
                    body=response_json,
                    response_time=response_time,
                    headers=dict(resp.headers)
                )
                
                if resp.status == 200:
                    if "token" not in response_json:
                        raise APIError(resp.status, "No access token in response")
                    return response_json["token"]
                else:
                    error_message = response_json.get("message", response_body) if isinstance(response_json, dict) else response_body
                    raise APIError(resp.status, error_message)
                    
        except aiohttp.ClientError as e:
            logger.error(f"❌ Network error: {str(e)}")
            raise APIError(500, f"Network error: {str(e)}")
        except Exception as e:
            if not isinstance(e, APIError):
                logger.error(f"❌ Unexpected error: {str(e)}")
            raise

async def get_order_by_id(order_id: str, token: str) -> Dict[str, Any]:
    """Get order details by ID."""
    url = f"{ORDER_BASE_URL}/{order_id}"
    start_time = time.time()
    
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {token}"
    }

    # Log request
    await log_request(
        method="GET",
        url=url,
        headers=headers
    )

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, headers=headers) as resp:
                response_time = time.time() - start_time
                response_body = await resp.text()
                
                try:
                    response_json = json.loads(response_body)
                except json.JSONDecodeError:
                    response_json = response_body

                # Log response
                await log_response(
                    status=resp.status,
                    body=response_json,
                    response_time=response_time,
                    headers=dict(resp.headers)
                )
                
                if resp.status == 200:
                    logger.info(f"✅ ORDER DETAILS - Successfully retrieved order {order_id}")
                    logger.debug(f"ORDER DETAILS - Response data: {json.dumps(response_json, indent=2)[:500]}...")
                    return response_json
                else:
                    error_message = response_json.get("message", response_body) if isinstance(response_json, dict) else response_body
                    logger.error(f"❌ ORDER ERROR - Failed to get order {order_id}: {error_message}")
                    raise APIError(resp.status, error_message)
                    
        except aiohttp.ClientError as e:
            logger.error(f"❌ ORDER NETWORK ERROR - Failed to fetch order {order_id}: {str(e)}")
            logger.debug(f"ORDER ERROR - Full exception: {repr(e)}")
            raise APIError(500, f"Network error: {str(e)}")
        except Exception as e:
            if not isinstance(e, APIError):
                logger.error(f"❌ ORDER UNEXPECTED ERROR - Order {order_id}: {str(e)}")
                logger.debug(f"ORDER ERROR - Full exception: {repr(e)}")
            raise

async def create_otp(phone: str) -> bool:
    """Create OTP for the given phone number."""
    url = f"{OTP_BASE_URL}/otp/create"
    start_time = time.time()
    
    headers = {
        "RobotXAuthToken": ROBOT_X_AUTH_TOKEN,
        "Content-Type": "application/json"
    }
    
    data = {
        "target": phone
    }

    # Log request
    await log_request(
        method="POST",
        url=url,
        headers=headers,
        data=data
    )

    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, json=data, headers=headers, ssl=False) as resp:
                response_time = time.time() - start_time
                response_body = await resp.text()
                
                try:
                    response_json = json.loads(response_body)
                except json.JSONDecodeError:
                    response_json = response_body

                # Log response
                await log_response(
                    status=resp.status,
                    body=response_json,
                    response_time=response_time,
                    headers=dict(resp.headers)
                )
                
                if resp.status == 200:
                    logger.info(f"✅ OTP created successfully for phone {phone}")
                    return True
                else:
                    error_message = response_json.get("message", response_body) if isinstance(response_json, dict) else response_body
                    logger.error(f"❌ Failed to create OTP for phone {phone}: {error_message}")
                    raise APIError(resp.status, error_message)
                    
        except aiohttp.ClientError as e:
            logger.error(f"❌ Network error creating OTP: {str(e)}")
            raise APIError(500, f"Network error: {str(e)}")
        except Exception as e:
            if not isinstance(e, APIError):
                logger.error(f"❌ Unexpected error creating OTP: {str(e)}")
            raise

async def verify_otp(phone: str, otp: str) -> bool:
    """Verify OTP for the given phone number."""
    url = f"{OTP_BASE_URL}/otp/verify"
    start_time = time.time()
    
    headers = {
        "RobotXAuthToken": ROBOT_X_AUTH_TOKEN,
        "Content-Type": "application/json"
    }
    
    data = {
        "target": phone,
        "otp": otp
    }

    # Log request
    await log_request(
        method="POST",
        url=url,
        headers=headers,
        data=data
    )

    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, json=data, headers=headers, ssl=False) as resp:
                response_time = time.time() - start_time
                response_body = await resp.text()
                
                try:
                    response_json = json.loads(response_body)
                except json.JSONDecodeError:
                    response_json = response_body

                # Log response
                await log_response(
                    status=resp.status,
                    body=response_json,
                    response_time=response_time,
                    headers=dict(resp.headers)
                )
                
                if resp.status == 200:
                    logger.info(f"✅ OTP verified successfully for phone {phone}")
                    return True
                else:
                    error_message = response_json.get("message", response_body) if isinstance(response_json, dict) else response_body
                    logger.error(f"❌ Failed to verify OTP for phone {phone}: {error_message}")
                    raise APIError(resp.status, error_message)
                    
        except aiohttp.ClientError as e:
            logger.error(f"❌ Network error verifying OTP: {str(e)}")
            raise APIError(500, f"Network error: {str(e)}")
        except Exception as e:
            if not isinstance(e, APIError):
                logger.error(f"❌ Unexpected error verifying OTP: {str(e)}")
            raise
