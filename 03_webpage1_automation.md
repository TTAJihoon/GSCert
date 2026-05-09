# 웹페이지1 자동화 설계

## 대상 주소

`http://210.96.71.85`

에이전트에서 항상 로그인 설정이 되어 있는 상태를 전제로 한다.

## 프로젝트 폴더 선택

프로젝트 폴더는 `#edm-folder` 내부의 `a` 요소로 표시된다.

예시 outerHTML:

```html
<a parentoid="1PkGjaJBU1i" oid="1PlIJs-Wpgv" foldermode="N" opcodes="" lastmodifiedat="1774922790000" name="00009 TTA-26-00009(완료) 우리데이터 주식회사(우리데이터클리닉 V1.0)" fullpathindex="#0030U0L0005" flagshortcut="false" existfavorite="false" managergroupoid="E000" href="javascript:app.edm.contents.update({OID:'1PlIJs-Wpgv', folderType:'C', init: true});" fullpathname="" foldertype="C" menuname="edm-folder-context-tree" class="jstree-clicked"><ins class="jstree-icon">&nbsp;</ins>00009 TTA-26-00009(완료) 우리데이터 주식회사(우리데이터클리닉 V1.0)</a>
```

위치 기반 selector는 프로젝트 순서가 바뀌면 위험하므로 자동화에서는 사용하지 않는다.

위험한 예:

```text
#edm-folder > ul > li... > li:nth-child(1) > a
```

권장 방식:

```text
#edm-folder 내부에서 프로젝트번호를 포함하는 a 요소를 찾는다.
```

예:

```text
TTA-26-00009
```

프로젝트번호는 아래 형식의 문자열이다.

```text
TTA-26-00009
```

자동화에서는 DB의 `프로젝트번호` 값을 그대로 사용해 프로젝트 폴더명을 찾는다.

## 문서 전체 선택

프로젝트 폴더 선택 후 현재 페이지에 표시된 목록이 폴더 전체 파일 목록이다.

전체 선택 체크박스:

```html
<input type="checkbox" name="document-list-select-all" events="document-list-select-all-change">
```

selector:

```text
#main-list-document > table > thead > tr > th.document-list-header-checkbox > input[type=checkbox]
```

## 파일 다운로드 메뉴 표시

체크박스 선택 후 특정 버튼을 누르면 해당 버튼 아래로 메뉴가 표시된다.

메뉴 표시 버튼 기본 상태:

```html
<div class="contents-title-btn-text contents-title-btn-more fg-button hcursor" id="menu-folder-list-drop" href="#contents-title-btn-more" title="고급" menuname="edm-main-context-menu"></div>
```

selector:

```text
#menu-folder-list-drop
```

메뉴 표시 버튼 활성 상태:

```html
<div class="contents-title-btn-text contents-title-btn-more fg-button hcursor menu-item-area active" id="menu-folder-list-drop" href="#contents-title-btn-more" title="고급" menuname="edm-main-context-menu"></div>
```

부모 요소:

```html
<div class="contents-title-btns-right">
  <div class="contents-title-btn-text contents-title-btn-more fg-button hcursor menu-item-area active" id="menu-folder-list-drop" href="#contents-title-btn-more" title="고급" menuname="edm-main-context-menu"></div>
  <div class="contents-title-btn-text contents-title-btn-createFolder hcursor" title="새폴더" events="createFolder-click"></div>
  <div class="contents-title-btn-text contents-title-btn-createDoc hcursor" title="새문서" events="createDoc-click"></div>
</div>
```

부모 selector:

```text
#main-list-menu > div.contents-title-panel-content > div.contents-title-btns.contents-title-btns-bg > div.contents-title-btns-right
```

## 파일 다운로드 메뉴 항목

메뉴의 파일 다운로드 항목:

```html
<li class="menuEvent" menuevent="saveDocumentsFileAll"><span class="icon ico_menu_down"></span>파일 다운로드</li>
```

selector:

```text
#edm-main-context-menu > li:nth-child(10)
```

`menuevent="saveDocumentsFileAll"` 속성은 항상 존재하는 것으로 확인되었다.

따라서 자동화에서는 `li:nth-child(10)`보다 아래 selector를 우선 사용한다.

```text
#edm-main-context-menu li[menuevent="saveDocumentsFileAll"]
```

## selector 우선순위

파일 다운로드 메뉴 실행 시 아래 순서로 selector를 사용한다.

1. 메뉴 표시 버튼: `#menu-folder-list-drop`
2. 파일 다운로드 항목: `#edm-main-context-menu li[menuevent="saveDocumentsFileAll"]`
3. 보조 파일 다운로드 항목: `#edm-main-context-menu > li:nth-child(10)`

## 권장 자동화 방식

1. `#edm-folder` 내부에서 프로젝트번호 포함 폴더를 찾는다.
2. 해당 폴더를 클릭한다.
3. 문서 목록 로딩 완료를 기다린다.
4. 전체 선택 체크박스를 클릭한다.
5. `#menu-folder-list-drop` 버튼을 클릭한다.
6. `#edm-main-context-menu`가 표시될 때까지 기다린다.
7. `menuevent="saveDocumentsFileAll"` 항목을 우선 찾아 클릭한다.
8. Windows 폴더 선택 팝업이 표시될 때까지 기다린다.

## 남은 확인 필요

- 메뉴 클릭 후 Windows 폴더 선택 팝업이 뜨기까지 평균 소요 시간
- 문서 목록이 비어 있는 프로젝트가 있는지 여부
