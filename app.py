import streamlit as st
import pandas as pd
import plotly.express as px
import s3fs
import gcsfs
import json
import os

st.title('Cloud Bucket Browser (S3/GCS): View CSV/XLS(X) as Tables and Graphs')

# ----------------------------
# Helpers
# ----------------------------
ALLOWED_EXTS = {'.csv', '.xls', '.xlsx'}
EXPECTED_TIME_SERIES = {'Frame Number', 'Procrustes Similarity', 'Joint Angle Distance'}

def detect_scheme(url: str) -> str:
    if not url:
        return ''
    if url.startswith('s3://'):
        return 's3'
    if url.startswith('gs://'):
        return 'gs'
    return ''

def clean_prefix(path: str) -> str:
    if not path:
        return path
    path = path.strip()
    path = path.rstrip('/') + '/'
    return path

def strip_scheme(url: str):
    # returns (scheme, without_scheme)
    if url.startswith('s3://'):
        return 's3', url[len('s3://'):]
    if url.startswith('gs://'):
        return 'gs', url[len('gs://'):]
    return '', url

def rebuild_url(scheme: str, without_scheme: str) -> str:
    return f"{scheme}://{without_scheme}"

def basename_from_path(p: str) -> str:
    p = p.rstrip('/')
    return p.rsplit('/', 1)[-1] if '/' in p else p

def is_allowed_file(name: str) -> bool:
    lname = name.lower()
    return any(lname.endswith(ext) for ext in ALLOWED_EXTS)

def get_fs(scheme: str, *, anon: bool,
           aws_access_key_id: str = '', aws_secret_access_key: str = '', aws_session_token: str = '', region_name: str = '',
           gcs_token=None):
    if scheme == 's3':
        if anon:
            return s3fs.S3FileSystem(anon=True)
        kwargs = {}
        if aws_access_key_id and aws_secret_access_key:
            kwargs.update(dict(key=aws_access_key_id, secret=aws_secret_access_key, token=aws_session_token or None))
        if region_name:
            kwargs.update(dict(client_kwargs={'region_name': region_name}))
        return s3fs.S3FileSystem(**kwargs)
    if scheme == 'gs':
        token = 'anon' if anon else (gcs_token if gcs_token is not None else 'google_default')
        return gcsfs.GCSFileSystem(token=token)
    raise ValueError("Unsupported scheme. Use s3:// or gs://")

def build_storage_options(scheme: str, *, anon: bool,
                          aws_access_key_id: str = '', aws_secret_access_key: str = '', aws_session_token: str = '', region_name: str = '',
                          gcs_token=None) -> dict:
    if scheme == 's3':
        opts = {'anon': bool(anon)}
        if not anon:
            if aws_access_key_id and aws_secret_access_key:
                opts.update({'key': aws_access_key_id, 'secret': aws_secret_access_key})
            if aws_session_token:
                opts['token'] = aws_session_token
        if region_name:
            opts['client_kwargs'] = {'region_name': region_name}
        return opts
    if scheme == 'gs':
        token = 'anon' if anon else (gcs_token if gcs_token is not None else 'google_default')
        return {'token': token}
    return {}

def list_cloud(fs, scheme: str, prefix: str):
    # Returns (dirs, files) with full scheme:// paths
    try:
        _, without = strip_scheme(prefix)
        items = fs.ls(without, detail=True)
    except Exception as e:
        st.error(f"Failed to list '{prefix}': {e}")
        return [], []
    dirs_set, files = set(), []
    for it in items:
        name = it.get('name') or it.get('Key') or ''
        full_without = name  # e.g. 'bucket/path/file.csv'
        rel = full_without[len(without):] if full_without.startswith(without) else full_without
        # If provider supplies explicit directory type
        if it.get('type') == 'directory' or full_without.endswith('/'):
            dirs_set.add(rebuild_url(scheme, full_without.rstrip('/') + '/'))
            continue
        # Derive child dirs from first component in rel
        if '/' in rel:
            child = rel.split('/', 1)[0]
            dirs_set.add(rebuild_url(scheme, without.rstrip('/') + '/' + child.strip('/') + '/'))
        else:
            full_url = rebuild_url(scheme, full_without)
            if is_allowed_file(full_url):
                files.append(full_url)
    dirs = sorted(dirs_set, key=lambda x: x.lower())
    files.sort(key=lambda x: x.lower())
    return dirs, files

def read_any(path: str) -> pd.DataFrame:
    storage_options = st.session_state.get('storage_options', {})
    if path.lower().endswith('.csv'):
        return pd.read_csv(path, storage_options=storage_options)
    return pd.read_excel(path, storage_options=storage_options)

def plot_bar_interactive(df: pd.DataFrame, label_col: str, stat_col: str, title: str):
    fig = px.bar(df, x=label_col, y=stat_col, title=title, text=stat_col)
    fig.update_traces(texttemplate='%{text:.2f}', textposition='outside',
                      hovertemplate=f'{label_col}: %{{x}}<br>{stat_col}: %{{y}}')
    fig.update_layout(xaxis_tickangle=-45)
    st.plotly_chart(fig, use_container_width=True)

def validate_and_plot_bar_interactive(df: pd.DataFrame, label_col: str, stat_col: str, title: str):
    if stat_col not in df.columns or label_col not in df.columns:
        st.warning("Selected columns not found in the data.")
        return
    if not pd.api.types.is_numeric_dtype(df[stat_col]):
        st.warning(f"The selected statistic column '{stat_col}' is not numeric.")
        return
    plot_bar_interactive(df, label_col, stat_col, title)

def plot_csv_line_chart(df: pd.DataFrame):
    fig = px.line(
        df,
        x='Frame Number',
        y=['Procrustes Similarity', 'Joint Angle Distance'],
        labels={'value': 'Metric Value', 'Frame Number': 'Frame Number', 'variable': 'Metric'},
        title='Metrics over Frames'
    )
    st.plotly_chart(fig, use_container_width=True)

def plot_generic_lines(df: pd.DataFrame, title: str):
    num_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    if not num_cols:
        st.info("No numeric columns to plot.")
        return
    fig = px.line(df[num_cols], title=title)
    st.plotly_chart(fig, use_container_width=True)

# ----------------------------
# Sidebar: connection + nav
# ----------------------------
st.sidebar.header("Bucket connection (gs:// for GCS, s3:// for AWS)")

default_path = st.session_state.get('default_path', '')
bucket_input = st.sidebar.text_input("Bucket or prefix (gs://bucket/path/ or s3://bucket/path/)", value=default_path, placeholder="gs://your-bucket/some/prefix/")

scheme = detect_scheme(bucket_input)

if scheme == 's3':
    col_auth1, col_auth2 = st.sidebar.columns(2)
    public = col_auth1.checkbox("Public (anonymous)", value=True, key="s3_public")
    region_name = col_auth2.text_input("Region (optional)", value="", key="s3_region")

    aws_access_key_id = ""
    aws_secret_access_key = ""
    aws_session_token = ""
    if not public:
        aws_access_key_id = st.sidebar.text_input("AWS Access Key ID", value="", type="default")
        aws_secret_access_key = st.sidebar.text_input("AWS Secret Access Key", value="", type="password")
        aws_session_token = st.sidebar.text_input("AWS Session Token (optional)", value="", type="default")

elif scheme == 'gs':
    col_auth1, _ = st.sidebar.columns(2)
    public = col_auth1.checkbox("Public (anonymous)", value=True, key="gs_public")
    creds_file = None
    if not public:
        creds_file = st.sidebar.file_uploader("Service Account JSON", type=['json'])
        st.sidebar.caption("Or use Google Default Credentials via gcloud.")
else:
    st.sidebar.info("Enter a path starting with gs:// (Google Cloud) or s3:// (AWS).")
    public = True
    region_name = ""
    aws_access_key_id = aws_secret_access_key = aws_session_token = ""
    creds_file = None

connect = st.sidebar.button("Connect")

if connect and scheme:
    st.session_state['default_path'] = bucket_input
    st.session_state['prefix'] = clean_prefix(bucket_input)
    if scheme == 's3':
        fs = get_fs(
            scheme='s3',
            anon=public,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            aws_session_token=aws_session_token,
            region_name=region_name
        )
        st.session_state['fs'] = fs
        st.session_state['scheme'] = 's3'
        st.session_state['storage_options'] = build_storage_options(
            's3',
            anon=public,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            aws_session_token=aws_session_token,
            region_name=region_name
        )
    elif scheme == 'gs':
        # Connect handler for GCS
        if not public and creds_file is None and os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") is None:
            st.error("Upload a Service Account JSON or run 'gcloud auth application-default login' before connecting.")
            st.stop()
        token = 'anon' if public else (json.load(creds_file) if creds_file else 'google_default')
        fs = get_fs(scheme='gs', anon=public, gcs_token=token)
        st.session_state['fs'] = fs
        st.session_state['scheme'] = 'gs'
        st.session_state['storage_options'] = {'token': token}

# Initialize defaults if not set
fs = st.session_state.get('fs')
current_prefix = st.session_state.get('prefix', '')
current_scheme = st.session_state.get('scheme', detect_scheme(current_prefix))

# ----------------------------
# Main UI
# ----------------------------
if not fs or not current_prefix or not current_scheme:
    st.info("Enter your bucket/prefix (gs:// or s3://) and click Connect.")
else:
    st.subheader("Browse folders")
    st.caption(f"Current prefix: {current_prefix}")

    # Breadcrumbs: allow going up one level
    up_col, refresh_col = st.columns([1,1])
    if up_col.button("⬆️ Go up one level"):
        scheme, without = strip_scheme(current_prefix)
        parts = without.rstrip('/').split('/')
        if len(parts) > 1:
            new_without = '/'.join(parts[:-1]) + '/'
        else:
            new_without = parts[0] + '/'
        st.session_state['prefix'] = rebuild_url(scheme, new_without)
        current_prefix = st.session_state['prefix']
    if refresh_col.button("🔄 Refresh"):
        pass

    dirs, files = list_cloud(fs, current_scheme, current_prefix)

    # Folder selection
    if dirs:
        folder_names = [basename_from_path(d.rstrip('/')) for d in dirs]
        selected_folder = st.selectbox("Folders", options=["(stay here)"] + folder_names, index=0, key="folder_select")
        open_btn = st.button("Open selected folder")
        if open_btn and selected_folder != "(stay here)":
            idx = folder_names.index(selected_folder)
            st.session_state['prefix'] = dirs[idx]
            current_prefix = st.session_state['prefix']
            dirs, files = list_cloud(fs, current_scheme, current_prefix)
    else:
        st.write("No subfolders.")

    st.subheader("Files (CSV/XLS/XLSX)")
    if not files:
        st.write("No CSV/Excel files in this folder.")
    else:
        file_labels = [basename_from_path(f) for f in files]
        selected_labels = st.multiselect("Select up to 2 files", options=file_labels, default=[])
        selected_indices = [file_labels.index(lbl) for lbl in selected_labels]
        selected_files = [files[i] for i in selected_indices][:2]
        if len(selected_labels) > 2:
            st.warning("You selected more than 2 files. Only the first 2 will be used.")

        visualize = st.button("Load and visualize")
        if visualize and selected_files:
            for fp in selected_files:
                st.markdown(f"### {basename_from_path(fp)}")
                try:
                    df = read_any(fp)
                except Exception as e:
                    st.error(f"Failed to read {fp}: {e}")
                    continue

                st.dataframe(df.head(50), use_container_width=True)

                if EXPECTED_TIME_SERIES.issubset(df.columns):
                    plot_csv_line_chart(df)
                else:
                    num_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
                    cand_label_cols = [c for c in df.columns if df[c].dtype == 'object' and df[c].nunique() <= max(50, int(len(df)*0.8))]
                    if num_cols and cand_label_cols:
                        label_col = cand_label_cols[0]
                        stat_col = num_cols[0]
                        validate_and_plot_bar_interactive(df, label_col, stat_col, title=f"Bar: {label_col} vs {stat_col}")
                    else:
                        plot_generic_lines(df, title="Line plot (numeric columns)")