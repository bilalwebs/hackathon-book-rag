"""
Personalization API - Adjust content based on user experience level (+50 points)
Uses configured chat provider
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.services.llm_provider import llm_provider

router = APIRouter()


class PersonalizeRequest(BaseModel):
    content: str
    software_experience: str
    hardware_experience: str


class PersonalizeResponse(BaseModel):
    personalized_content: str
    adjustments_made: list[str]


@router.post("/", response_model=PersonalizeResponse)
async def personalize_content(request: PersonalizeRequest):
    """
    Personalize content based on user's experience level
    - Beginner: More explanations, simpler terminology
    - Intermediate: Balanced technical depth
    - Advanced: Concise, assumes prior knowledge
    """
    try:
        system_prompt = f"""You are an expert technical educator. Adjust the following educational content to match the reader's experience level:

Software Experience: {request.software_experience}
Hardware Experience: {request.hardware_experience}

Guidelines:
- For Beginners: Add more explanations, use analogies, define technical terms, include step by step details
- For Intermediate: Balance technical depth with clarity, assume some prior knowledge
- For Advanced: Be concise, use advanced terminology, focus on nuances and edge cases

Preserve all code examples, images, and links. Only adjust explanatory text.
Return the adjusted content in the same format (Markdown)."""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": request.content}
        ]

        personalized_content = llm_provider.generate_chat_completion(messages, temperature=0.7, max_tokens=3000)

        adjustments = []
        if request.software_experience == "Beginner":
            adjustments.append("Added detailed explanations for software concepts")
        elif request.software_experience == "Advanced":
            adjustments.append("Increased technical depth and assumed prior software knowledge")

        if request.hardware_experience == "Beginner":
            adjustments.append("Simplified hardware terminology and added practical analogies")
        elif request.hardware_experience == "Advanced":
            adjustments.append("Focused on advanced hardware integration details")

        return PersonalizeResponse(
            personalized_content=personalized_content,
            adjustments_made=adjustments
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"Personalization error: {e}")
        raise HTTPException(status_code=500, detail=f"Personalization failed: {str(e)}")
