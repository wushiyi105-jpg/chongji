FROM python:3.10-slim

LABEL org.opencontainers.image.source="https://github.com/wushiyi105-jpg/chongji"
LABEL org.opencontainers.image.description="宠记 · 宠物照护,RER/DER 喂食量、免疫日历与症状分级"
LABEL org.opencontainers.image.licenses="MIT"

WORKDIR /app

COPY . .

RUN pip install -e .

EXPOSE 8000

CMD ["python", "-m", "chongji", "web", "--host", "0.0.0.0"]
