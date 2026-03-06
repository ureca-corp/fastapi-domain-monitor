# fastapi-domain-monitor

Real-time `Mermaid classDiagram` monitoring for Pydantic and SQLModel projects running on FastAPI.

- Mount directly inside an existing FastAPI app
- Rebuild diagrams automatically when model files change
- Support `compact` and `full` detail modes
- Show classes, enums, inheritance, relationships, notes, and source excerpts

## Table Of Contents

### English

1. Overview
2. Installation
3. Quick Start
4. Recommended Project Layout
5. FastAPI Integration Options
6. Standalone Mode
7. Local Development Notes

### 한국어

1. 소개
2. 설치
3. 빠른 시작
4. 권장 프로젝트 구조
5. FastAPI 연동 옵션
6. 단독 실행 모드
7. 로컬 개발 시 주의사항

---

## English

### Overview

`fastapi-domain-monitor` is a development tool that parses Python source code with AST and renders a live `Mermaid classDiagram` for your Pydantic and SQLModel classes.

It is designed for projects where you want to:

- inspect domain models while coding
- follow schema changes in real time
- expose a browser-based class diagram inside your FastAPI app
- review relationships, inheritance, defaults, notes, and source excerpts quickly

### Installation

#### Install from PyPI with `uv`

```bash
uv add fastapi-domain-monitor
```

#### Install from PyPI with `pip`

```bash
pip install fastapi-domain-monitor
```

#### Install from a local checkout in editable mode

This is useful when you are developing the library and your app together.

```bash
uv add --editable /path/to/fastapi-domain-monitor
```

or

```bash
pip install -e /path/to/fastapi-domain-monitor
```

### Quick Start

Add the monitor to your FastAPI app:

```python
from fastapi import FastAPI
from fastapi_domain_monitor import setup_domain_monitor

app = FastAPI()

setup_domain_monitor(
    app,
    watch_dirs=["src/modules"],
)
```

Run your app:

```bash
uv run uvicorn src.main:app --reload
```

Open:

```txt
http://127.0.0.1:8000/domain-monitor
```

### Recommended Project Layout

By default, the monitor watches these file patterns:

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

Example:

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

### FastAPI Integration Options

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

Important options:

- `watch_dirs`: root directories to scan
- `watch_patterns`: file globs to parse
- `mount_path`: dashboard path, default is `/domain-monitor`
- `detail_level`: `compact` or `full`
- `show_base_fields`: show common fields like `id`, `created_at`
- `enabled`: easy environment-based switch

### Standalone Mode

You can also run the monitor as a separate local server:

```bash
domain-monitor start -w src/modules
```

Example with more options:

```bash
domain-monitor start \
  -w src/modules \
  --watch-pattern models.py \
  --watch-pattern schemas.py \
  --detail-level full \
  --show-base-fields \
  --port 7842
```

Open:

```txt
http://127.0.0.1:7842/domain-monitor
```

### Local Development Notes

- This package is intended for development-time visualization.
- `uvicorn --reload` usually watches only your application directory.
- If you install this package as an editable local dependency and modify the library itself, your app server may need a restart before changes appear.

### Links

- PyPI: [fastapi-domain-monitor](https://pypi.org/project/fastapi-domain-monitor/)
- Repository: [ureca-corp/fastapi-domain-monitor](https://github.com/ureca-corp/fastapi-domain-monitor)

---

## 한국어

### 소개

`fastapi-domain-monitor`는 Python 소스를 AST로 파싱해서 Pydantic / SQLModel 클래스를 실시간 `Mermaid classDiagram`으로 보여주는 개발용 도구입니다.

이런 경우에 적합합니다.

- 도메인 모델 구조를 브라우저에서 바로 확인하고 싶을 때
- 모델 파일 변경이 다이어그램에 즉시 반영되길 원할 때
- FastAPI 앱 내부에 다이어그램 대시보드를 붙이고 싶을 때
- 관계선, 상속, 기본값, note, 소스 코드를 빠르게 확인하고 싶을 때

### 설치

#### PyPI에서 `uv`로 설치

```bash
uv add fastapi-domain-monitor
```

#### PyPI에서 `pip`로 설치

```bash
pip install fastapi-domain-monitor
```

#### 로컬 소스를 editable 모드로 설치

라이브러리와 사용하는 앱을 동시에 개발할 때 편합니다.

```bash
uv add --editable /path/to/fastapi-domain-monitor
```

또는

```bash
pip install -e /path/to/fastapi-domain-monitor
```

### 빠른 시작

FastAPI 앱에 `setup_domain_monitor()`를 붙입니다.

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

브라우저에서 접속합니다.

```txt
http://127.0.0.1:8000/domain-monitor
```

### 권장 프로젝트 구조

기본 감시 패턴은 아래와 같습니다.

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

예시:

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

### FastAPI 연동 옵션

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
- `watch_patterns`: 파싱할 파일 패턴 목록
- `mount_path`: 대시보드 경로, 기본값은 `/domain-monitor`
- `detail_level`: `compact` 또는 `full`
- `show_base_fields`: `id`, `created_at` 같은 공통 필드 표시 여부
- `enabled`: 환경별 on/off 스위치

### 단독 실행 모드

앱 내부에 마운트하지 않고 모니터만 따로 띄울 수도 있습니다.

```bash
domain-monitor start -w src/modules
```

옵션 예시:

```bash
domain-monitor start \
  -w src/modules \
  --watch-pattern models.py \
  --watch-pattern schemas.py \
  --detail-level full \
  --show-base-fields \
  --port 7842
```

접속 주소:

```txt
http://127.0.0.1:7842/domain-monitor
```

### 로컬 개발 시 주의사항

- 이 패키지는 개발 중 시각화 도구입니다.
- `uvicorn --reload`는 보통 현재 앱 디렉터리만 감시합니다.
- 이 패키지를 editable 로컬 dependency로 연결해 두고 라이브러리 자체를 수정하는 경우, 앱 서버를 한 번 재시작해야 반영될 수 있습니다.

### 링크

- PyPI: [fastapi-domain-monitor](https://pypi.org/project/fastapi-domain-monitor/)
- 저장소: [ureca-corp/fastapi-domain-monitor](https://github.com/ureca-corp/fastapi-domain-monitor)
