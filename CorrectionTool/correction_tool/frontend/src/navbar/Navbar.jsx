import "./navbar.css"
import { useNavigate } from "react-router-dom";
function Navbar({username, project_name, completionData}) {
    const userIsAdmin = JSON.parse(localStorage.getItem("user_role")) === "admin";
    const navigate = useNavigate();
        function handleSignout() {
        console.log("Singning out")
        localStorage.removeItem("username");
        localStorage.removeItem("project_name");
        navigate("/");
        navigate(0);
    }

    if (username != null) {
        return (
            <nav className="navbar">
                    <div className="navbar-project">WORKING ON:
                         <span className="navbar-project-internal">{project_name === null ? "Choose a project" : project_name}</span></div>
                    {
                        ((completionData.total_num !== null) && (
                        <div className="navbar-middle">
                            <span className="navbar-completion">Corrected by you: {completionData.total_corrected_by_user}
                                  ({(completionData.total_corrected_by_user * 100 / completionData.total_num).toFixed(2) }%)</span>
                            <span className="navbar-completion">Total Corrected: {completionData.total_corrected}</span>
                            <span className="navbar-completion">Total Documents: {completionData.total_num}</span>
                        </div>
                    ))
                    }
                    <div className="navbar-right">
                        {userIsAdmin && (
                            <div className="navbar-admin" onClick={() => navigate("/admin_overview")}>Admin</div>
                        )}
                        <div className="navbar-analytics" onClick={() => navigate("/history")}>History</div>
                        <div className="navbar-username" onClick={() => navigate("/")}>{username}</div>
                        <div className="navbar-signout" onClick={() => handleSignout()}>Signout</div>
                    </div>
            </nav>
        )
    } else {
        return (
            <nav className="navbar">
                <div className="navbar-content">
                    <div className="navbar-project">HITL Data Correction Tool</div>
                </div>
            </nav>
        )
    }

}

export default Navbar;