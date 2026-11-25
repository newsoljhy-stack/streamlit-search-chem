'''
import streamlit as st
import pandas as pd
import hashlib
from sqlalchemy import create_engine, text

# 1. 웹 페이지 기본 레이아웃 설정
st.set_page_config(page_title="Supabase 화학물질 매핑 시스템", layout="wide")

# 2. 인증 및 상태 관리를 위한 세션 변수 초기화
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
if "user_fullname" not in st.session_state:
    st.session_state["user_fullname"] = ""
if "auth_mode" not in st.session_state:
    st.session_state["auth_mode"] = "login"  # login 또는 signup 상태 추적

# 3. Supabase DB 연결 엔진 초기화 (문자열 파싱 에러 원천 차단)
DB_URI = "postgresql://postgres.tfowutksytpzarkxhvxl:jeO4tg2HfSyE5W9I@aws-0-ap-northeast-2.pooler.supabase.com:5432/postgres"

@st.cache_resource
def get_supabase_engine():
    """커넥션 풀 엔진을 재사용하여 안정성 유지"""
    return create_engine(DB_URI, pool_pre_ping=True)

# 🔒 [보안] 비밀번호 SHA-256 해싱 함수
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

# 🔑 [인증] Supabase DB 회원 데이터 검증 함수 (로그인)
def verify_user_from_db(username: str, password_raw: str):
    if not username.strip() or not password_raw.strip():
        return None
    
    engine = get_supabase_engine()
    pwd_hash = hash_password(password_raw)
    
    query = """
    SELECT user_name_ko 
    FROM public.dashboard_users 
    WHERE username = :username AND password_hash = :password_hash;
    """
    
    with engine.connect() as conn:
        result = conn.execute(text(query), {"username": username, "password_hash": pwd_hash}).fetchone()
        
    return result[0] if result else None

# 📝 [등록] Supabase DB 회원가입 처리 함수
def register_user_to_db(username: str, password_raw: str, name_ko: str):
    engine = get_supabase_engine()
    pwd_hash = hash_password(password_raw)
    
    # 중복 아이디 체크 쿼리
    check_query = "SELECT username FROM public.dashboard_users WHERE username = :username;"
    # 신규 회원 인서트 쿼리
    insert_query = """
    INSERT INTO public.dashboard_users (username, password_hash, user_name_ko)
    VALUES (:username, :password_hash, :name_ko);
    """
    
    with engine.begin() as conn:  # 트랜잭션 자동 커밋을 위해 engine.begin() 사용
        # 1. 중복 체크
        existing = conn.execute(text(check_query), {"username": username}).fetchone()
        if existing:
            return "duplicate"
        
        # 2. 회원 등록
        conn.execute(text(insert_query), {
            "username": username,
            "password_hash": pwd_hash,
            "name_ko": name_ko
        })
        return "success"

# 🧪 [검색] 화학물질 라이브 검색 데이터 로드 함수
def search_supabase_chemical(keyword: str):
    if not keyword.strip():
        return pd.DataFrame()
    
    engine = get_supabase_engine()
    query = """
    SELECT m.cas_no AS "CAS 번호",
           m.ke_no AS "기존물질번호",
           MAX(CASE WHEN n.language = 'ko' THEN n.chemical_name END) AS "한글 물질명",
           MAX(CASE WHEN n.language = 'en' THEN n.chemical_name END) AS "영문 물질명",
           m.is_existing_chemical AS "기존물질여부"
    FROM public.chemical_master m
    JOIN public.chemical_names n ON m.cas_no = n.cas_no
    WHERE m.cas_no IN (
        SELECT DISTINCT cas_no
        FROM public.chemical_names
        WHERE chemical_name ILIKE :keyword1 OR cas_no ILIKE :keyword2
    )
    GROUP BY m.cas_no, m.ke_no, m.is_existing_chemical
    ORDER BY m.cas_no ASC
    LIMIT 100;
    """
    search_param = f"%{keyword}%"
    
    with engine.connect() as conn:
        df = pd.read_sql_query(
            sql=text(query),
            con=conn,
            params={"keyword1": search_param, "keyword2": search_param}
        )
    return df

# [화면 분기 로직 1] 로그인 / 회원가입 컴포넌트
if not st.session_state["logged_in"]:
    
    # 1️⃣ 로그인 모드일 때
    if st.session_state["auth_mode"] == "login":
        st.markdown("<h2 style='text-align: center;'>🔐 시스템 로그인</h2>", unsafe_allow_html=True)
        
        with st.form(key="login_form", clear_on_submit=False):
            username = st.text_input("아이디 (계정명)")
            password = st.text_input("비밀번호", type="password")
            login_button = st.form_submit_button("로그인", use_container_width=True)
            
            if login_button:
                with st.spinner("사용자 정보를 확인하는 중..."):
                    user_fullname = verify_user_from_db(username, password)
                    if user_fullname:
                        st.session_state["logged_in"] = True
                        st.session_state["user_fullname"] = user_fullname
                        st.success(f"🎉 {user_fullname}님 환영합니다!")
                        st.rerun()
                    else:
                        st.error("❌ 아이디 또는 비밀번호가 올바르지 않습니다.")
        
        # 회원가입 전환 버튼
        if st.button("계정이 없으신가요? 신규 회원가입", use_container_width=True):
            st.session_state["auth_mode"] = "signup"
            st.rerun()

    # 2️⃣ 회원가입 모드일 때
    elif st.session_state["auth_mode"] == "signup":
        st.markdown("<h2 style='text-align: center;'>📝 신규 회원가입</h2>", unsafe_allow_html=True)
        
        with st.form(key="signup_form", clear_on_submit=False):
            new_username = st.text_input("사용할 아이디 (영문/숫자 중심)")
            new_name_ko = st.text_input("성함 (실명)")
            new_password = st.text_input("비밀번호 설정", type="password")
            confirm_password = st.text_input("비밀번호 확인", type="password")
            signup_button = st.form_submit_button("가입 신청하기", use_container_width=True)
            
            if signup_button:
                if not new_username.strip() or not new_password.strip() or not new_name_ko.strip():
                    st.warning("⚠️ 모든 빈칸을 입력해 주세요.")
                elif new_password != confirm_password:
                    st.error("❌ 비밀번호 확인이 일치하지 않습니다.")
                else:
                    with st.spinner("Supabase에 계정을 생성하는 중..."):
                        status = register_user_to_db(new_username, new_password, new_name_ko)
                        if status == "success":
                            st.success("✅ 회원가입이 완료되었습니다! 로그인해 주세요.")
                            st.session_state["auth_mode"] = "login"  # 로그인 창으로 자동 전환
                            st.rerun()
                        elif status == "duplicate":
                            st.error("❌ 이미 존재하는 아이디입니다. 다른 아이디를 입력해 주세요.")
        
        # 로그인 돌아가기 버튼
        if st.button("이미 계정이 있습니다. 로그인으로 이동", use_container_width=True):
            st.session_state["auth_mode"] = "login"
            st.rerun()

# [화면 분기 로직 2] 로그인 후 메인 대시보드 인터페이스
else:
    # 사이드바 메뉴 구성
    with st.sidebar:
        st.subheader(f"👤 로그인 사용자")
        st.info(f"**{st.session_state['user_fullname']}** 관리자님")
        if st.button("🚪 로그아웃", use_container_width=True):
            st.session_state["logged_in"] = False
            st.session_state["user_fullname"] = ""
            st.rerun()
            
    # 메인 대시보드 상단 제목
    st.title("🧪 Supabase 화학물질 통합 검색 (엔터/버튼 전송)")
    st.write("사용자가 조회를 요청할 때만 클라우드 Supabase DB에 직접 연결하여 비용과 성능을 최적화합니다.")
    
    # st.form을 사용하여 실시간 트리거 방지
    with st.form(key="search_form", clear_on_submit=False):
        col1, col2 = st.columns([0.8, 0.2])
        with col1:
            search_query = st.text_input("🔍 검색어를 입력하세요 (물질명 또는 CAS 번호)", "")
        with col2:
            st.write("")
            st.write("") 
            submit_button = st.form_submit_button(label="검색하기", use_container_width=True)
            
    # 결과 출력 로직
    if submit_button and search_query:
        with st.spinner("Supabase에서 데이터를 안전하게 불러오는 중..."):
            result_df = search_supabase_chemical(search_query)
            if not result_df.empty:
                st.success(f"Supabase 검색 완료: 총 {len(result_df)}건의 라이브 데이터가 매치되었습니다.")
                
                # 다운로드 기능
                csv = result_df.to_csv(index=False).encode('utf-8-sig')
                st.download_button(
                    label="📥 현재 검색 결과 다운로드 (CSV)",
                    data=csv,
                    file_name=f"supabase_search_{search_query}.csv",
                    mime="text/csv",
                )
                # 테이블 출력
                st.dataframe(result_df, use_container_width=True)
            else:
                st.warning(f"'{search_query}'에 일치하는 화학물질 데이터가 Supabase에 존재하지 않습니다.")
                
    elif submit_button and not search_query:
        st.warning("검색어를 한 글자 이상 입력한 후 검색해 주세요.")
    else:
        st.info("💡 위의 검색창에 검색어를 입력한 후 [엔터]를 누르거나 [검색하기] 버튼을 클릭하세요.")
'''

import streamlit as st
import pandas as pd
import hashlib
from sqlalchemy import create_engine, text

# 1. 웹 페이지 기본 레이아웃 설정
st.set_page_config(page_title="Supabase 화학물질 매핑 시스템", layout="wide")

# 2. 인증 및 상태 관리를 위한 세션 변수 초기화
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
if "user_fullname" not in st.session_state:
    st.session_state["user_fullname"] = ""
if "auth_mode" not in st.session_state:
    st.session_state["auth_mode"] = "login"

# 3. Supabase DB 연결 엔진 초기화
# 주의: 실제 배포 시에는 DB_URI를 코드에 직접 노출하지 말고 st.secrets["DB_URI"]를 사용하세요.
DB_URI = "postgresql://postgres.tfowutksytpzarkxhvxl:jeO4tg2HfSyE5W9I@aws-0-ap-northeast-2.pooler.supabase.com:5432/postgres"

@st.cache_resource
def get_supabase_engine():
    """커넥션 풀 엔진을 재사용하여 안정성 유지"""
    return create_engine(DB_URI, pool_pre_ping=True)

# 🔒 [보안] 비밀번호 SHA-256 해싱 함수
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

# 🔑 [인증] Supabase DB 회원 데이터 검증 함수 (로그인)
def verify_user_from_db(username: str, password_raw: str):
    if not username.strip() or not password_raw.strip():
        return None
    engine = get_supabase_engine()
    pwd_hash = hash_password(password_raw)
    query = """
        SELECT user_name_ko FROM public.dashboard_users 
        WHERE username = :username AND password_hash = :password_hash;
    """
    with engine.connect() as conn:
        result = conn.execute(text(query), {"username": username, "password_hash": pwd_hash}).fetchone()
        return result[0] if result else None

# 📝 [등록] Supabase DB 회원가입 처리 함수
def register_user_to_db(username: str, password_raw: str, name_ko: str):
    engine = get_supabase_engine()
    pwd_hash = hash_password(password_raw)
    check_query = "SELECT username FROM public.dashboard_users WHERE username = :username;"
    insert_query = """
        INSERT INTO public.dashboard_users (username, password_hash, user_name_ko)
        VALUES (:username, :password_hash, :name_ko);
    """
    with engine.begin() as conn:
        existing = conn.execute(text(check_query), {"username": username}).fetchone()
        if existing:
            return "duplicate"
        conn.execute(text(insert_query), {
            "username": username,
            "password_hash": pwd_hash,
            "name_ko": name_ko
        })
        return "success"

# 🧪 [검색] BM25 기반 관련도 랭킹 화학물질 검색 함수
def search_supabase_chemical_bm25(keyword: str):
    clean_kw = keyword.strip()
    if not clean_kw:
        return pd.DataFrame()
    
    no_space_kw = clean_kw.replace(" ", "")
    engine = get_supabase_engine()
    
    # 오타 허용 및 BM25 하이브리드 랭킹 쿼리
    # - WHERE 절에 similarity() > 0.25 조건을 추가하여 오타가 있어도 검색 결과에 포함
    # - word_similarity(): 긴 화학물질명 안에 검색어와 비슷한 단어 덩어리가 있을 때 높은 점수 부여
    query = """
        WITH scored_matches AS (
            SELECT 
                cas_no,
                MAX(
                    -- 1) 완전 일치 보너스 (공백 무시)
                    CASE 
                        WHEN REPLACE(LOWER(chemical_name), ' ', '') = LOWER(:no_space_kw) 
                             OR cas_no = :exact_kw 
                        THEN 12.0 ELSE 0.0 
                    END +
                    -- 2) 부분 문자열 포함 보너스 (오타 없는 일반 검색 시 상위 노출 보장)
                    CASE 
                        WHEN REPLACE(chemical_name, ' ', '') ILIKE :no_space_like 
                             OR cas_no ILIKE :like_kw 
                        THEN 4.0 ELSE 0.0 
                    END +
                    -- 3) BM25 핵심: 문서 길이 정규화 랭킹 (TF-IDF)
                    ts_rank_cd(to_tsvector('simple', chemical_name), plainto_tsquery('simple', :exact_kw), 32) * 5.0 +
                    -- 4) 전체 문자열 Trigram 유사도 (오타 교정 핵심 점수)
                    similarity(REPLACE(LOWER(chemical_name), ' ', ''), LOWER(:no_space_kw)) * 6.0 +
                    -- 5) 부분 단어 Trigram 유사도 (긴 복합명 속 오타 단어 포착)
                    word_similarity(LOWER(:no_space_kw), REPLACE(LOWER(chemical_name), ' ', '')) * 3.0
                ) AS relevance_score
            FROM public.chemical_names
            WHERE 
                -- 기본 포함 검색 (공백 포함/무시)
                chemical_name ILIKE :like_kw 
                OR cas_no ILIKE :like_kw
                OR REPLACE(chemical_name, ' ', '') ILIKE :no_space_like
                OR to_tsvector('simple', chemical_name) @@ plainto_tsquery('simple', :exact_kw)
                -- [확장] 오타 허용 조건: 3글자 이상 입력 시 유사도 0.25 이상이면 오타라도 검색 허용
                OR (
                    LENGTH(:no_space_kw) >= 3 
                    AND (
                        similarity(REPLACE(LOWER(chemical_name), ' ', ''), LOWER(:no_space_kw)) >= 0.25
                        OR word_similarity(LOWER(:no_space_kw), REPLACE(LOWER(chemical_name), ' ', '')) >= 0.45
                    )
                )
            GROUP BY cas_no
        )
        SELECT 
            m.cas_no AS "CAS 번호",
            m.ke_no AS "기존물질번호",
            MAX(CASE WHEN n.language = 'ko' THEN n.chemical_name END) AS "한글 물질명",
            MAX(CASE WHEN n.language = 'en' THEN n.chemical_name END) AS "영문 물질명",
            m.is_existing_chemical AS "기존물질여부",
            ROUND(s.relevance_score::numeric, 3) AS "연관도 점수"
        FROM public.chemical_master m
        JOIN public.chemical_names n ON m.cas_no = n.cas_no
        JOIN scored_matches s ON m.cas_no = s.cas_no
        GROUP BY m.cas_no, m.ke_no, m.is_existing_chemical, s.relevance_score
        ORDER BY s.relevance_score DESC, m.cas_no ASC
        LIMIT 100;
    """
    
    params = {
        "exact_kw": clean_kw,
        "like_kw": f"%{clean_kw}%",
        "no_space_kw": no_space_kw,
        "no_space_like": f"%{no_space_kw}%"
    }
    
    with engine.connect() as conn:
        df = pd.read_sql_query(sql=text(query), con=conn, params=params)
    return df

# [화면 분기 로직 1] 로그인 / 회원가입 컴포넌트
if not st.session_state["logged_in"]:
    if st.session_state["auth_mode"] == "login":
        st.markdown("<h2 style='text-align: center;'>🔐 시스템 로그인</h2>", unsafe_allow_html=True)
        with st.form(key="login_form", clear_on_submit=False):
            username = st.text_input("아이디 (계정명)")
            password = st.text_input("비밀번호", type="password")
            login_button = st.form_submit_button("로그인", use_container_width=True)
            
            if login_button:
                with st.spinner("사용자 정보를 확인하는 중..."):
                    user_fullname = verify_user_from_db(username, password)
                    if user_fullname:
                        st.session_state["logged_in"] = True
                        st.session_state["user_fullname"] = user_fullname
                        st.success(f"🎉 {user_fullname}님 환영합니다!")
                        st.rerun()
                    else:
                        st.error("❌ 아이디 또는 비밀번호가 올바르지 않습니다.")
                        
        if st.button("계정이 없으신가요? 신규 회원가입", use_container_width=True):
            st.session_state["auth_mode"] = "signup"
            st.rerun()

    elif st.session_state["auth_mode"] == "signup":
        st.markdown("<h2 style='text-align: center;'>📝 신규 회원가입</h2>", unsafe_allow_html=True)
        with st.form(key="signup_form", clear_on_submit=False):
            new_username = st.text_input("사용할 아이디 (영문/숫자 중심)")
            new_name_ko = st.text_input("성함 (실명)")
            new_password = st.text_input("비밀번호 설정", type="password")
            confirm_password = st.text_input("비밀번호 확인", type="password")
            signup_button = st.form_submit_button("가입 신청하기", use_container_width=True)
            
            if signup_button:
                if not new_username.strip() or not new_password.strip() or not new_name_ko.strip():
                    st.warning("⚠️ 모든 빈칸을 입력해 주세요.")
                elif new_password != confirm_password:
                    st.error("❌ 비밀번호 확인이 일치하지 않습니다.")
                else:
                    with st.spinner("Supabase에 계정을 생성하는 중..."):
                        status = register_user_to_db(new_username, new_password, new_name_ko)
                        if status == "success":
                            st.success("✅ 회원가입이 완료되었습니다! 로그인해 주세요.")
                            st.session_state["auth_mode"] = "login"
                            st.rerun()
                        elif status == "duplicate":
                            st.error("❌ 이미 존재하는 아이디입니다. 다른 아이디를 입력해 주세요.")
                            
        if st.button("이미 계정이 있습니다. 로그인으로 이동", use_container_width=True):
            st.session_state["auth_mode"] = "login"
            st.rerun()

# [화면 분기 로직 2] 로그인 후 메인 대시보드 인터페이스
else:
    with st.sidebar:
        st.subheader("👤 로그인 사용자")
        st.info(f"**{st.session_state['user_fullname']}** 관리자님")
        if st.button("🚪 로그아웃", use_container_width=True):
            st.session_state["logged_in"] = False
            st.session_state["user_fullname"] = ""
            st.rerun()

    st.title("🧪 Supabase 화학물질 통합 검색 (BM25 랭킹 적용)")
    st.write("검색어와의 연관도(BM25 점수)가 높은 순으로 화학물질을 정렬하여 보여줍니다.")

    with st.form(key="search_form", clear_on_submit=False):
        col1, col2 = st.columns([0.8, 0.2])
        with col1:
            search_query = st.text_input("🔍 검색어를 입력하세요 (물질명 또는 CAS 번호)", "")
        with col2:
            st.write("")
            st.write("")
            submit_button = st.form_submit_button(label="검색하기", use_container_width=True)

    if submit_button and search_query:
        with st.spinner("BM25 알고리즘으로 관련도 높은 데이터를 분석 중..."):
            result_df = search_supabase_chemical_bm25(search_query)
            if not result_df.empty:
                st.success(f"Supabase 검색 완료: 연관도 상위 {len(result_df)}건의 데이터가 매치되었습니다.")
                
                csv = result_df.to_csv(index=False).encode('utf-8-sig')
                st.download_button(
                    label="📥 현재 검색 결과 다운로드 (CSV)",
                    data=csv,
                    file_name=f"supabase_bm25_search_{search_query}.csv",
                    mime="text/csv",
                )
                
                st.dataframe(result_df, use_container_width=True)
            else:
                st.warning(f"'{search_query}'에 일치하는 화학물질 데이터가 Supabase에 존재하지 않습니다.")
    elif submit_button and not search_query:
        st.warning("검색어를 한 글자 이상 입력한 후 검색해 주세요.")
    else:
        st.info("💡 위의 검색창에 검색어를 입력한 후 [엔터]를 누르거나 [검색하기] 버튼을 클릭하세요.")

# streamlit run e:/vscode_workspace/2026_workspace/supabase_ex/spdy_filing_search_dash3.py
