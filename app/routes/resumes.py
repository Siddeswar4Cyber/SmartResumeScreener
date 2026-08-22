from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.services.file_parser import (
    FileParsingError,
    MAX_FILE_SIZE,
    parse_resume_file,
)

router = APIRouter(
    prefix="/api/resumes",
    tags=["Resumes"],
)
MAX_FILES_PER_REQUEST = 10

@router.post("/extract")
async def extract_resumes(
    files: list[UploadFile] = File(
        ...,
        description="One or more PDF or TXT resume files."
    ),
):
    """
    Upload resumes and extract their text.
    
    Successful and unsuccessful files are returned separately so one invalid resume does not prevent other resumes from processed.
    """

    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Upload at least one resume.",
        )

    if len(files)>MAX_FILES_PER_REQUEST:
        raise HTTPException(
            status_code = status.HTTP_400_BAD_REQUEST,
            detail=(
                f"A maximum of {MAX_FILES_PER_REQUEST} resumes can be proccesed at once."
            ),
        )

    successful_files = []
    failed_files = []

    for uploaded_file in files:
        filename = uploaded_file.filename or "unknown-file"

        try:
            # +1 for detecting files exceeding 5MB.
            
            file_content = await uploaded_file.read(MAX_FILE_SIZE+1)
            parsed_file = parse_resume_file(
                original_filename=filename,
                file_content=file_content,
            )

            successful_files.append(
                {
                    "filename": parsed_file.filename,
                    "file_type": parsed_file.file_type,
                    "page_count": parsed_file.page_count,
                    "character_count": parsed_file.character_count,
                    "extracted_text": parsed_file.text,
                }
            )
        except FileParsingError as error:
            failed_files.append(
                {
                    "filename": filename,
                    "error": str(error),
                }
            )

        except Exception as e:
            print(e)
            failed_files.append(
                {
                    "filename": filename,
                    "error": "An unexcepted error occured while reading the file.",
                }
            )

        finally:
            await uploaded_file.close()

    if not successful_files:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "None of the uploaded resumes could be processed.",
                "failed_files": failed_files
            }
        )

    return {
        "message": "Resume extraction completed",
        "processed_count": len(successful_files),
        "failed_count": len(failed_files),
        "successful_files": successful_files,
        "failed_files": failed_files
    }