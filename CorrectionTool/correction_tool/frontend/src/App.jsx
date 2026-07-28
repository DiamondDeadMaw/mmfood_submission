import { BrowserRouter as Router, Routes, Route, useNavigate } from "react-router-dom";
import { useState, useEffect } from "react";
import "./App.css";
import Navbar from "./navbar/Navbar.jsx";
import InteractionButton from "./components/InteractionButton.jsx";
import TextInput from "./components/TextInput.jsx";
import { makePostRequest } from "./constants.js";
import CorrectionPage from "./pages/correction/CorrectionPage.jsx";
import AdminReviewPage from "./pages/review/AdminReviewPage.jsx";
import History from "./pages/history/History.jsx";

function LoginFlow({ setLoggedIn, setUsername }) {
  async function handleLogin(username, password) {
    const response = await makePostRequest("login", {
      username: username,
      password: password,
    });
    if (response.success) {
      setUsername(username);
      localStorage.setItem("username", JSON.stringify(username));
      localStorage.setItem("user_role", JSON.stringify(response.user_role));
      setLoggedIn(true);
    } else {
      alert("Login failed: " + response.message);
    }
  }

  const [selectedUsername, setSelectedUsername] = useState("");
  const [selectedPassword, setSelectedPassowrd] = useState("");

  return (
    <div className="home-interaction-container">
      <h2 className="card-header">Login</h2>
      <TextInput
        setValue={setSelectedUsername}
        placeholder="Enter username"
        onKeyDown={(e) =>
          e.key === "Enter" && handleLogin(selectedUsername, selectedPassword)
        }
      />
      <TextInput
        setValue={setSelectedPassowrd}
        placeholder="Enter password"
        onKeyDown={(e) =>
          e.key === "Enter" && handleLogin(selectedUsername, selectedPassword)
        }
      />
      <InteractionButton
        text={"Login"}
        onButtonPress={handleLogin}
        args={[selectedUsername, selectedPassword]}
      />
    </div>
  );
}

function ProjectSelectionFlow({ username, setProjectName }) {
  const [allProjects, setAllProjects] = useState([]);
  const [newProject, setNewProject] = useState("");
  const navigate = useNavigate();
  useEffect(() => {
    async function fetchProjects() {
      const response = await makePostRequest("get_user_projects", {
        username: username,
      });
      
      if (response.ok) {
        setAllProjects(response.projects);
      } else {
        alert("Failed to fetch projects: " + response.message);
      }
    }

    fetchProjects();
  }, [username]);

  async function handleCreateProject() {
    if (
      newProject.trim() === "" ||
      newProject === null ||
      newProject === undefined ||
      newProject === "undefined"
    ) {
      alert("Project name cannot be empty");
      return;
    }
    const response = await makePostRequest("add_user_project", {
      username: username,
      project_name: newProject,
    });
    if (response.ok) {
      setProjectName(newProject);
      localStorage.setItem("project_name", JSON.stringify(newProject));
      setAllProjects([...allProjects, newProject]);
      setNewProject("");
    } else {
      alert("Failed to create project: " + response.message);
    }
  }

  function handleSetProjectName(text) {
    setProjectName(text);
    localStorage.setItem("project_name", JSON.stringify(text));
    navigate("/correction");
  }

  function ProjectSelect({ text }) {
    return (
      <div
        className="project-select-element"
        onClick={() => handleSetProjectName(text)}
      >
        {text}
      </div>
    );
  }

  return (
    <div className="home-interaction-container">
      <h2 className="card-header">Select a Project</h2>
      <div className="project-selection-container"
       style={
        allProjects.length === 0? {
          justifyContent: "end"
        } : {}
      }
      >
        {allProjects.map((project, index) => (
        <ProjectSelect key={index} text={project} />
      ))}
      <div className="row">
        <TextInput
          setValue={setNewProject}
          placeholder="Or create a new project"
          width={"70%"}
        />
        <InteractionButton
          text={"Create"}
          onButtonPress={handleCreateProject}
          args={[newProject]}
          width={"30%"}
          color={"#4CAF50"}
        />
      </div>
      </div>
    </div>
  );
}

function HomePage({ loggedIn, setLoggedIn, setUsername, setProjectName }) {
  if (!loggedIn) {
    return <LoginFlow setLoggedIn={setLoggedIn} setUsername={setUsername} />;
  } else {
    return (
      <ProjectSelectionFlow
        username={JSON.parse(localStorage.getItem("username"))}
        setProjectName={setProjectName}
      />
    );
  }
}

function App() {
  const [username, setUsername] = useState(() => {
    const storedUsername = localStorage.getItem("username");
    return storedUsername ? JSON.parse(storedUsername) : null;
  });

  const [projectName, setProjectName] = useState(() => {
    const storedProjectName = localStorage.getItem("project_name");
    return storedProjectName ? JSON.parse(storedProjectName) : null;
  });

  const [loggedIn, setLoggedIn] = useState(() => {
    return username !== null;
  });

  const [completionData, setCompletionData] = useState({
    total_num: null,
    total_corrected: null,
    total_corrected_by_user: null,
  });

  return (
    <div className="main-container">
      <Router>
      <Navbar username={username} project_name={projectName} completionData={completionData} />
     <div className="content-container">
        <Routes>
          <Route
            path="/"
            element={
              <HomePage
                loggedIn={loggedIn}
                setLoggedIn={setLoggedIn}
                setUsername={setUsername}
                setProjectName={setProjectName}
              />
            }
          />
          <Route
            path="/correction"
            element={
              <CorrectionPage username={username} projectName={projectName} setCompletionData={setCompletionData} />
            }
          />
          <Route
          path="/history"
          element={<History />}
          />
          <Route
            path="/admin_overview"
            element={
              <AdminReviewPage
                adminUsername={username}
              />
            }
          />
        </Routes>
     </div>
      </Router>
    </div>
  );
}

export default App;
