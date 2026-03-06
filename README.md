# fastapi-domain-monitor

FastAPI 앱에 붙여서 Pydantic / SQLModel 클래스를 실시간으로 `Mermaid classDiagram`으로 보여주는 개발용 대시보드입니다.

- FastAPI 앱 내부에 바로 마운트 가능
- 파일 변경 감지 후 다이어그램 자동 갱신
- `compact` / `full` 상세도 지원
- Pydantic, SQLModel, Enum, 상속, 관계선, note, source viewer 지원

## 설치

새 프로젝트에서 가장 간단한 설치 방법입니다.

### uv

```bash
uv add fastapi-domain-monitor
```

### pip

```bash
pip install fastapi-domain-monitor
```

### 로컬 소스 editable 설치

라이브러리와 사용하는 앱을 동시에 개발할 때는 editable 설치가 편합니다.

```bash
uv add --editable /path/to/fastapi-domain-monitor
```

또는

```bash
pip install -e /path/to/fastapi-domain-monitor
```

## 가장 빠른 사용법

FastAPI 앱에 `setup_domain_monitor()`를 한 번 마운트하면 됩니다.

```python
from fastapi import FastAPI
from fastapi_domain_monitor import setup_domain_monitor

app = FastAPI()

setup_domain_monitor(
    app,
    watch_dirs=["src/modules"],
)
```

앱을 실행합니다.

```bash
uv run uvicorn src.main:app --reload
```

브라우저에서 아래 주소를 엽니다.

```txt
http://127.0.0.1:8000/domain-monitor
```

## 권장 프로젝트 구조

기본적으로 아래 패턴의 파일들을 감시합니다.

```txt
*_models.py
models.py
*_schemas.py
schemas.py
*_entities.py
entities.py
*_dto.py
dto.py
```

예를 들어 이런 구조면 바로 동작합니다.

```txt
src/
  modules/
    accounts/
      models.py
    exams/
      schemas.py
    billing/
      dto.py
```

## 상세 옵션

```python
from fastapi import FastAPI
from fastapi_domain_monitor import setup_domain_monitor

app = FastAPI()

setup_domain_monitor(
    app,
    watch_dirs=["src/modules", "src/domains"],
    watch_patterns=["models.py", "schemas.py", "dto.py"],
    mount_path="/domain-monitor",
    detail_level="compact",   # "compact" | "full"
    show_base_fields=False,
    enabled=True,
)
```

주요 옵션:

- `watch_dirs`: 감시할 루트 디렉터리 목록
- `watch_patterns`: 감시할 파일 패턴 목록
- `mount_path`: 대시보드 마운트 경로. 기본값은 `/domain-monitor`
- `detail_level`: `compact` 또는 `full`
- `show_base_fields`: `id`, `created_at` 같은 공통 필드 표시 여부
- `enabled`: 환경별로 쉽게 끄기 위한 스위치

## standalone 실행

앱에 직접 마운트하지 않고, 모니터만 따로 띄울 수도 있습니다.

```bash
domain-monitor start -w src/modules
```

자주 쓰는 옵션:

```bash
domain-monitor start \
  -w src/modules \
  --watch-pattern models.py \
  --watch-pattern schemas.py \
  --detail-level full \
  --show-base-fields \
  --port 7842
```

standalone 모드 기본 주소:

```txt
http://127.0.0.1:7842/domain-monitor
```

## 새 프로젝트에서 로컬 실행 예시

`src/main.py`

```python
from fastapi import FastAPI
from fastapi_domain_monitor import setup_domain_monitor

app = FastAPI()

setup_domain_monitor(
    app,
    watch_dirs=["src/modules"],
    detail_level="compact",
)


@app.get("/health")
def health():
    return {"ok": True}
```

실행:

```bash
uv run uvicorn src.main:app --reload
```

접속:

```txt
http://127.0.0.1:8000/domain-monitor
```

## 주의사항

- 이 라이브러리는 개발용 시각화 도구입니다.
- `uvicorn --reload`는 보통 현재 앱 디렉터리만 감시합니다.
- editable dependency로 붙여서 라이브러리 소스를 직접 수정하는 경우, 사용하는 앱 서버는 한 번 재시작해야 변경이 반영될 수 있습니다.

## 배포

PyPI:

- [fastapi-domain-monitor](https://pypi.org/project/fastapi-domain-monitor/)

Repository:

- [ureca-corp/fastapi-domain-monitor](https://github.com/ureca-corp/fastapi-domain-monitor)
