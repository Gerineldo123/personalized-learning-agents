import json

from services.rag_service import seed_course_knowledge_base


def main() -> None:
    status = seed_course_knowledge_base()
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
