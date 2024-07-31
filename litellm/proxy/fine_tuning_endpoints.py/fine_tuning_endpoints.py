#########################################################################

#                          /v1/fine_tuning Endpoints

# Equivalent of https://platform.openai.com/docs/api-reference/fine-tuning
##########################################################################

import asyncio
import traceback
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import fastapi
import httpx
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)

import litellm
from litellm import CreateFileRequest, FileContentRequest
from litellm._logging import verbose_proxy_logger
from litellm.batches.main import FileObject
from litellm.proxy._types import *
from litellm.proxy.auth.user_api_key_auth import user_api_key_auth

router = APIRouter()

from litellm.llms.fine_tuning_apis.openai import (
    FineTuningJob,
    FineTuningJobCreate,
    OpenAIFineTuningAPI,
)


@router.post(
    "/v1/fine_tuning/jobs",
    dependencies=[Depends(user_api_key_auth)],
    tags=["fine-tuning"],
)
@router.post(
    "/fine_tuning/jobs",
    dependencies=[Depends(user_api_key_auth)],
    tags=["fine-tuning"],
)
async def create_fine_tuning_job(
    request: Request,
    fastapi_response: Response,
    fine_tuning_job: FineTuningJobCreate,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
):
    """
    Creates a fine-tuning job which begins the process of creating a new model from a given dataset.
    This is the equivalent of POST https://api.openai.com/v1/fine_tuning/jobs

    Supports Identical Params as: https://platform.openai.com/docs/api-reference/fine-tuning/create

    Example Curl:
    ```
    curl http://localhost:4000/v1/fine_tuning/jobs \
      -H "Content-Type: application/json" \
      -H "Authorization: Bearer sk-1234" \
      -d '{
        "model": "gpt-3.5-turbo",
        "training_file": "file-abc123",
        "hyperparameters": {
          "n_epochs": 4
        }
      }'
    ```
    """
    from litellm.proxy.proxy_server import (
        add_litellm_data_to_request,
        general_settings,
        get_custom_headers,
        proxy_config,
        proxy_logging_obj,
        version,
    )

    try:
        # Convert Pydantic model to dict
        data = fine_tuning_job.dict(exclude_unset=True)

        # Include original request and headers in the data
        data = await add_litellm_data_to_request(
            data=data,
            request=request,
            general_settings=general_settings,
            user_api_key_dict=user_api_key_dict,
            version=version,
            proxy_config=proxy_config,
        )

        # For now, use custom_llm_provider=="openai" -> this will change as LiteLLM adds more providers for fine-tuning
        response = await litellm.acreate_fine_tuning_job(
            custom_llm_provider="openai", **data
        )

        ### ALERTING ###
        asyncio.create_task(
            proxy_logging_obj.update_request_status(
                litellm_call_id=data.get("litellm_call_id", ""), status="success"
            )
        )

        ### RESPONSE HEADERS ###
        hidden_params = getattr(response, "_hidden_params", {}) or {}
        model_id = hidden_params.get("model_id", None) or ""
        cache_key = hidden_params.get("cache_key", None) or ""
        api_base = hidden_params.get("api_base", None) or ""

        fastapi_response.headers.update(
            get_custom_headers(
                user_api_key_dict=user_api_key_dict,
                model_id=model_id,
                cache_key=cache_key,
                api_base=api_base,
                version=version,
                model_region=getattr(user_api_key_dict, "allowed_model_region", ""),
            )
        )

        return response
    except Exception as e:
        await proxy_logging_obj.post_call_failure_hook(
            user_api_key_dict=user_api_key_dict, original_exception=e, request_data=data
        )
        verbose_proxy_logger.error(
            "litellm.proxy.proxy_server.create_fine_tuning_job(): Exception occurred - {}".format(
                str(e)
            )
        )
        verbose_proxy_logger.debug(traceback.format_exc())
        if isinstance(e, HTTPException):
            raise ProxyException(
                message=getattr(e, "message", str(e.detail)),
                type=getattr(e, "type", "None"),
                param=getattr(e, "param", "None"),
                code=getattr(e, "status_code", status.HTTP_400_BAD_REQUEST),
            )
        else:
            error_msg = f"{str(e)}"
            raise ProxyException(
                message=getattr(e, "message", error_msg),
                type=getattr(e, "type", "None"),
                param=getattr(e, "param", "None"),
                code=getattr(e, "status_code", 500),
            )
