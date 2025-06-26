"""
Pydantic models for qPCR upload validation
"""
from pydantic import BaseModel, Field, EmailStr, validator
from typing import Literal, Optional
from datetime import datetime
import re


class ExperimentUpload(BaseModel):
    """Model for experiment metadata validation"""
    experiment_name: str = Field(
        ..., 
        min_length=3, 
        max_length=100,
        description="Name of the qPCR experiment"
    )
    analysis_type: Literal["delta_delta_ct", "absolute"] = Field(
        ...,
        description="Type of qPCR analysis to perform"
    )
    housekeeping_gene: str = Field(
        ..., 
        pattern="^[A-Za-z0-9-_]+$",
        max_length=50,
        description="Reference gene for normalization"
    )
    control_sample: str = Field(
        ..., 
        max_length=50,
        description="Control sample name for delta-delta CT"
    )
    user_email: EmailStr = Field(
        ...,
        description="Email for notifications"
    )
    description: Optional[str] = Field(
        None,
        max_length=500,
        description="Optional experiment description"
    )
    
    @validator('experiment_name')
    def validate_experiment_name(cls, v):
        """Ensure experiment name doesn't contain special characters"""
        if not re.match(r'^[A-Za-z0-9\s\-_]+$', v):
            raise ValueError('Experiment name can only contain letters, numbers, spaces, hyphens, and underscores')
        return v.strip()


class FileUploadMetadata(BaseModel):
    """Model for file upload validation"""
    file_size: int = Field(
        ..., 
        lt=20_000_000,  # 20MB limit
        gt=0,
        description="File size in bytes"
    )
    file_type: Literal["application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"] = Field(
        ...,
        description="Must be Excel format"
    )
    file_name: str = Field(
        ...,
        pattern=r'^[A-Za-z0-9\s\-_]+\.xlsx$',
        description="Excel file name"
    )


class UploadRequest(BaseModel):
    """Combined request model for upload endpoint"""
    experiment: ExperimentUpload
    file_metadata: FileUploadMetadata


class UploadResponse(BaseModel):
    """Response model for successful upload"""
    experiment_id: str
    upload_url: str
    upload_fields: dict
    message: str = "Upload URL generated successfully"
    expires_in: int = 3600  # seconds