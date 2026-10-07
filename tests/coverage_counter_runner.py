import contextlib
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import code_analyzer.cli as cli
from language_analyzers.core.serialization import architecture_to_dict

import ast
from language_analyzers.typescript import ast as ts
from language_analyzers.kotlin import ast as ka
COUNTS = dict(read=0, python_parse=0, typescript_parse=0, kotlin_parse=0)
original_ast_parse = ast.parse
def python_parse(*a, **kw):
    COUNTS['python_parse'] += 1
    return original_ast_parse(*a, **kw)
ast.parse = python_parse
class ParserProxy:
    def __init__(self, parser, kind): self.parser, self.kind = parser, kind
    def parse(self, *a, **kw):
        COUNTS[self.kind] += 1
        return self.parser.parse(*a, **kw)
original_ts_parser = ts.get_parser
ts.get_parser = lambda *a, **kw: ParserProxy(original_ts_parser(*a, **kw), 'typescript_parse')
original_kt_parser = ka.get_kotlin_parser
ka.get_kotlin_parser = lambda: ParserProxy(original_kt_parser(), 'kotlin_parse')

FILES = {
    'main.py': '''from fastapi import FastAPI, Depends
from sqlalchemy.orm import DeclarativeBase
class Base(DeclarativeBase): pass
class User(Base):
    __tablename__ = 'users'
def get_user(): return 1
app = FastAPI()
@app.get('/users')
def users(user=Depends(get_user)): return user
''',
    'src/main.ts': '''import { Module, Controller, Get, Injectable } from '@nestjs/common';
import { NestFactory } from '@nestjs/core';
@Injectable() export class Service { value() { return 1; } }
@Controller('users') export class C {
 constructor(private service: Service) {}
 @Get() users() { return this.service.value(); }
}
@Module({ controllers: [C], providers: [Service] }) export class Root {}
async function bootstrap() { const app = await NestFactory.create(Root); await app.listen(3000); }
bootstrap();
export async function load() { return fetch('/users'); }
''',
    'src/Screen.kt': '''package sample
import androidx.compose.runtime.Composable
import androidx.lifecycle.ViewModel
import androidx.room.Entity
import retrofit2.http.GET
@Entity(tableName = "users") data class User(val id: Int)
class MainViewModel : ViewModel() { fun load() = 1 }
@Composable fun Screen() { val x = MainViewModel().load() }
interface Api { @GET("/users") suspend fun users(): List<User> }
''',
    'alembic/versions/first.py': "from alembic import op\ndef upgrade():\n    op.add_column('users', object())\n",
    'notes.txt': 'Sample notes\n',
}
COMBINATIONS = {
    'python': ['-l', 'python'], 'typescript': ['-l', 'typescript'],
    'kotlin': ['-l', 'kotlin'], 'fastapi': ['-f', 'fastapi'],
    'android': ['-f', 'android'], 'sqlalchemy': ['-f', 'sqlalchemy'],
    'nestjs': ['-f', 'nestjs'],
    'fastapi-sqlalchemy': ['-f', 'fastapi', '-f', 'sqlalchemy'],
    'nestjs-typescript': ['-f', 'nestjs', '-l', 'typescript'],
    'android-kotlin': ['-f', 'android', '-l', 'kotlin', '--no-language-graph'],
}

def read(path, project):
    COUNTS['read'] += 1
    return FILES[path.relative_to(project).as_posix()]

def capture():
    project = Path('/private/tmp/network-analysis-coverage-characterization')
    project.mkdir(exist_ok=True)
    captured = {}
    for name, flags in COMBINATIONS.items():
        for granularity in ('file', 'symbol'):
            current = {}
            COUNTS.update(dict.fromkeys(COUNTS, 0))
            class Capture:
                def __init__(self, **kwargs): pass
                def render(self, arch, path, *, bottleneck_report=None):
                    current.update(COUNTS)
                    return Path(path)
            previous = sys.argv
            sys.argv = ['code-analyzer', str(project), *flags, '--granularity', granularity, '-o', str(project / 'out.html')]
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    cli.main(file_lister=lambda *args, **kw: ('provided', list(FILES)),
                             file_reader=lambda path: read(path, project),
                             renderer_factory=Capture)
            finally:
                sys.argv = previous
            captured[name + ':' + granularity] = current
    return captured

if __name__ == '__main__':
    target = Path(sys.argv[1])
    if target.exists(): raise RuntimeError('Refusing to replace captured data')
    target.write_text(json.dumps(capture(), ensure_ascii=False, indent=2, sort_keys=True))
