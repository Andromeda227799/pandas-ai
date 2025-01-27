from unittest.mock import MagicMock, Mock, mock_open, patch

import pandas as pd
import pytest
from numpy import False_

import pandasai
from pandasai.agent import Agent
from pandasai.dataframe.base import DataFrame
from pandasai.exceptions import PandaAIApiKeyError


class TestDataFrame:
    @pytest.fixture(autouse=True)
    def reset_current_agent(self):
        pandasai._current_agent = None
        yield
        pandasai._current_agent = None

    @pytest.fixture
    def sample_data(self):
        return {
            "Name": ["John", "Emma", "Liam", "Olivia", "Noah"],
            "Age": [28, 35, 22, 31, 40],
            "City": ["New York", "London", "Paris", "Tokyo", "Sydney"],
            "Salary": [75000, 82000, 60000, 79000, 88000],
        }

    @pytest.fixture
    def sample_df(self, sample_data):
        return DataFrame(
            sample_data,
            path="acme-corp/employees",
            name="employees",
            description="Employee data",
        )

    def test_dataframe_initialization(self, sample_data, sample_df):
        assert isinstance(sample_df, DataFrame)
        assert isinstance(sample_df, pd.DataFrame)
        assert sample_df.equals(pd.DataFrame(sample_data))

    def test_dataframe_operations(self, sample_df):
        assert len(sample_df) == 5
        assert list(sample_df.columns) == ["Name", "Age", "City", "Salary"]
        assert sample_df["Salary"].mean() == 76800

    @patch("pandasai.agent.Agent")
    @patch("os.environ")
    def test_chat_creates_agent(self, mock_env, mock_agent, sample_data):
        sample_df = DataFrame(sample_data)
        mock_env.return_value = {"PANDABI_API_URL": "localhost:8000"}
        sample_df.chat("Test query")
        mock_agent.assert_called_once_with([sample_df], config=sample_df.config)

    @patch("pandasai.Agent")
    def test_chat_reuses_existing_agent(self, sample_df):
        mock_agent = Mock(spec=Agent)
        sample_df._agent = mock_agent

        sample_df.chat("First query")
        assert sample_df._agent is not None
        initial_agent = sample_df._agent
        sample_df.chat("Second query")
        assert sample_df._agent is initial_agent

    def test_follow_up_without_chat_raises_error(self, sample_df):
        with pytest.raises(ValueError, match="No existing conversation"):
            sample_df.follow_up("Follow-up query")

    def test_follow_up_after_chat(self, sample_df):
        mock_agent = Mock(spec=Agent)
        sample_df._agent = mock_agent

        sample_df.follow_up("Follow-up query")
        assert mock_agent.follow_up.call_count == 1

    def test_chat_method(self, sample_df):
        mock_agent = Mock(spec=Agent)
        sample_df._agent = mock_agent

        sample_df.chat("Test question")

        assert sample_df._agent is not None
        assert mock_agent.chat.call_count == 1

    def test_chat_with_config(self, sample_df):
        config = {"max_retries": 100}
        with patch("pandasai.agent.Agent") as mock_agent:
            sample_df.chat("Test query", config=config)
            mock_agent.assert_called_once_with([sample_df], config=sample_df.config)
        assert sample_df.config.max_retries == 100

    def test_column_hash(self, sample_df):
        assert hasattr(sample_df, "column_hash")
        assert isinstance(sample_df.column_hash, str)
        assert len(sample_df.column_hash) == 32  # MD5 hash length

    @patch("pandasai.dataframe.base.get_pandaai_session")
    @patch("pandasai.dataframe.base.os.path.exists")
    @patch("pandasai.dataframe.base.open", new_callable=mock_open)
    @patch("pandasai.dataframe.base.os.environ")
    @patch("pandasai.dataframe.base.find_project_root")
    def test_push_successful(
        self,
        mock_find_project_root,
        mock_environ,
        mock_open,
        mock_path_exists,
        mock_get_session,
        sample_df,
    ):
        # Mock environment variable
        mock_environ.get.return_value = "fake_api_key"

        # Mock project root
        mock_find_project_root.return_value = "/fake/project/root"

        # Mock file paths
        mock_path_exists.side_effect = (
            lambda x: "data.parquet" in x
        )  # Only data.parquet exists

        # Mock session and POST request
        mock_session = MagicMock()
        mock_get_session.return_value = mock_session

        sample_df.push()

        # Verify POST request
        mock_session.post.assert_called_once_with(
            "/datasets/push",
            files=[
                (
                    "files",
                    ("schema.yaml", mock_open.return_value, "application/x-yaml"),
                ),
                (
                    "files",
                    (
                        "data.parquet",
                        mock_open.return_value,
                        "application/octet-stream",
                    ),
                ),
            ],
            params={
                "path": sample_df.path,
                "description": sample_df.description,
                "name": sample_df.name,
            },
            headers={
                "accept": "application/json",
                "x-authorization": "Bearer fake_api_key",
            },
        )

    def test_push_raises_error_if_path_is_none(self, sample_df):
        # Set up the object with no path
        sample_df.path = None

        # Call the method and assert the exception
        with pytest.raises(
            ValueError,
            match="Please save the dataset before pushing to the remote server.",
        ) as context:
            sample_df.push()

    @patch("pandasai.dataframe.base.os.environ")
    def test_push_raises_error_if_api_key_is_missing(self, mock_environ, sample_df):
        # Mock environment variable as missing
        mock_environ.get.return_value = None

        # Call the method and assert the exception
        with pytest.raises(PandaAIApiKeyError):
            sample_df.push()

    @patch("pandasai.dataframe.base.os.path.exists")
    @patch("pandasai.dataframe.base.open", new_callable=mock_open)
    @patch("pandasai.dataframe.base.get_pandaai_session")
    @patch("pandasai.dataframe.base.os.environ")
    def test_push_closes_files_on_completion(
        self,
        mock_environ,
        mock_get_session,
        mock_open,
        mock_path_exists,
        sample_df: DataFrame,
    ):
        # Mock environment variable
        mock_environ.get.return_value = "fake_api_key"
        # Mock file existence
        mock_path_exists.return_value = True

        # Mock session
        mock_session = MagicMock()
        mock_get_session.return_value = mock_session

        # Call the method
        sample_df.push()

        # Assert that files were closed after the request
        mock_open.return_value.close.assert_called()
