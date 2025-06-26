"""
qPCR Upload Handler Lambda Function
Processes file uploads and creates experiment records
"""
import json
import os
import uuid
from datetime import datetime, timedelta
import boto3
from botocore.exceptions import ClientError
from mangum import Mangum
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from models import UploadRequest, UploadResponse

# Initialize AWS clients
s3_client = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')

# Environment variables
UPLOAD_BUCKET = os.environ.get('UPLOAD_BUCKET', 'qpcr-uploads-dev')
EXPERIMENTS_TABLE = os.environ.get('DYNAMODB_TABLE', 'qpcr-experiments')
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'dev')

# Initialize FastAPI app
app = FastAPI(title="qPCR Upload Handler")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize DynamoDB table
experiments_table = dynamodb.Table(EXPERIMENTS_TABLE)


@app.post("/upload", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
async def create_upload(request: UploadRequest):
    """
    Create a presigned POST URL for S3 upload and store experiment metadata
    """
    try:
        # Generate unique experiment ID
        experiment_id = str(uuid.uuid4())
        timestamp = datetime.utcnow().isoformat()
        
        # Create S3 key for the file
        s3_key = f"experiments/{experiment_id}/{request.file_metadata.file_name}"
        
        # Generate presigned POST URL for S3 upload
        try:
            presigned_post = s3_client.generate_presigned_post(
                Bucket=UPLOAD_BUCKET,
                Key=s3_key,
                Fields={
                    'Content-Type': request.file_metadata.file_type,
                    'x-amz-meta-experiment-id': experiment_id,
                    'x-amz-meta-user-email': request.experiment.user_email,
                },
                Conditions=[
                    {'Content-Type': request.file_metadata.file_type},
                    ['content-length-range', 1, request.file_metadata.file_size + 1000],  # Allow slight overhead
                    {'x-amz-meta-experiment-id': experiment_id},
                ],
                ExpiresIn=3600  # 1 hour
            )
        except ClientError as e:
            print(f"Error generating presigned URL: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to generate upload URL"
            )
        
        # Store experiment metadata in DynamoDB
        try:
            # Calculate TTL (7 days from now)
            ttl_timestamp = int((datetime.utcnow() + timedelta(days=7)).timestamp())
            
            item = {
                'experimentId': experiment_id,
                'userId': request.experiment.user_email,
                'experimentName': request.experiment.experiment_name,
                'uploadTimestamp': timestamp,
                'inputFileKey': f"s3://{UPLOAD_BUCKET}/{s3_key}",
                'analysisType': request.experiment.analysis_type,
                'housekeepingGene': request.experiment.housekeeping_gene,
                'controlSample': request.experiment.control_sample,
                'status': 'uploaded',
                'fileName': request.file_metadata.file_name,
                'fileSize': request.file_metadata.file_size,
                'ttl': ttl_timestamp
            }
            
            # Add optional description if provided
            if request.experiment.description:
                item['description'] = request.experiment.description
            
            experiments_table.put_item(Item=item)
            
        except ClientError as e:
            print(f"Error storing experiment metadata: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to store experiment metadata"
            )
        
        # Return response with presigned POST data
        return UploadResponse(
            experiment_id=experiment_id,
            upload_url=presigned_post['url'],
            upload_fields=presigned_post['fields'],
            expires_in=3600
        )
        
    except Exception as e:
        print(f"Unexpected error in upload handler: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Upload processing failed: {str(e)}"
        )


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "environment": ENVIRONMENT,
        "bucket": UPLOAD_BUCKET,
        "table": EXPERIMENTS_TABLE
    }


# Lambda handler using Mangum
lambda_handler = Mangum(app)